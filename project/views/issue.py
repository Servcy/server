import json
import random
from collections import defaultdict
from itertools import chain

from django.contrib.postgres.aggregates import ArrayAgg
from django.contrib.postgres.fields import ArrayField
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError
from django.db.models import (
    BigIntegerField,
    Case,
    CharField,
    Exists,
    F,
    Func,
    Max,
    OuterRef,
    Prefetch,
    Q,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.gzip import gzip_page
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from common.permissions import (
    ProjectEntityPermission,
    ProjectLitePermission,
    ProjectMemberPermission,
)
from common.views import BaseAPIView, BaseViewSet
from iam.enums import ERole
from project.models import (
    CommentReaction,
    Issue,
    IssueActivity,
    IssueAttachment,
    IssueComment,
    IssueLink,
    IssueProperty,
    IssueReaction,
    IssueRelation,
    IssueSubscriber,
    Label,
    Project,
    ProjectMember,
)
from project.serializers import (
    CommentReactionSerializer,
    IssueActivitySerializer,
    IssueAttachmentSerializer,
    IssueCommentSerializer,
    IssueCreateSerializer,
    IssueDetailSerializer,
    IssueFlatSerializer,
    IssueLinkSerializer,
    IssuePropertySerializer,
    IssueReactionSerializer,
    IssueRelationSerializer,
    IssueSerializer,
    IssueSubscriberSerializer,
    LabelSerializer,
    RelatedIssueSerializer,
)
from project.tasks import issue_activity
from project.utils.filters import issue_filters


class IssueListEndpoint(BaseAPIView):
    permission_classes = [
        ProjectEntityPermission,
    ]

    def get(self, request, workspace_slug, project_id):
        issue_ids = request.GET.get("issues", False)

        if not issue_ids:
            return Response(
                {"error": "Issues are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        issue_ids = [issue_id for issue_id in issue_ids.split(",") if issue_id != ""]

        queryset = (
            Issue.issue_objects.filter(
                workspace__slug=workspace_slug, project_id=project_id, pk__in=issue_ids
            )
            .filter(workspace__slug=self.kwargs.get("workspace_slug"))
            .select_related("workspace", "project", "state", "parent")
            .prefetch_related("assignees", "labels", "issue_module__module")
            .annotate(cycle_id=F("issue_cycle__cycle_id"))
            .annotate(
                link_count=IssueLink.objects.filter(issue=OuterRef("id"))
                .order_by()
                .annotate(count=Func(F("id"), function="Count"))
                .values("count")
            )
            .annotate(
                attachment_count=IssueAttachment.objects.filter(issue=OuterRef("id"))
                .order_by()
                .annotate(count=Func(F("id"), function="Count"))
                .values("count")
            )
            .annotate(
                sub_issues_count=Issue.issue_objects.filter(parent=OuterRef("id"))
                .order_by()
                .annotate(count=Func(F("id"), function="Count"))
                .values("count")
            )
            .annotate(
                label_ids=Coalesce(
                    ArrayAgg(
                        "labels__id",
                        distinct=True,
                        filter=~Q(labels__id__isnull=True),
                    ),
                    Value([], output_field=ArrayField(BigIntegerField())),
                ),
                assignee_ids=Coalesce(
                    ArrayAgg(
                        "assignees__id",
                        distinct=True,
                        filter=~Q(assignees__id__isnull=True),
                    ),
                    Value([], output_field=ArrayField(BigIntegerField())),
                ),
                module_ids=Coalesce(
                    ArrayAgg(
                        "issue_module__module_id",
                        distinct=True,
                        filter=~Q(issue_module__module_id__isnull=True),
                    ),
                    Value([], output_field=ArrayField(BigIntegerField())),
                ),
            )
        ).distinct()

        filters = issue_filters(request.query_params, "GET")

        # Custom ordering for priority and state
        priority_order = ["urgent", "high", "medium", "low", "none"]
        state_order = [
            "backlog",
            "unstarted",
            "started",
            "completed",
            "cancelled",
        ]

        order_by_param = request.GET.get("order_by", "-created_at")

        issue_queryset = queryset.filter(**filters)

        # Priority Ordering
        if order_by_param == "priority" or order_by_param == "-priority":
            priority_order = (
                priority_order if order_by_param == "priority" else priority_order[::-1]
            )
            issue_queryset = issue_queryset.annotate(
                priority_order=Case(
                    *[
                        When(priority=p, then=Value(i))
                        for i, p in enumerate(priority_order)
                    ],
                    output_field=CharField(),
                )
            ).order_by("priority_order")

        # State Ordering
        elif order_by_param in [
            "state__name",
            "state__group",
            "-state__name",
            "-state__group",
        ]:
            state_order = (
                state_order
                if order_by_param in ["state__name", "state__group"]
                else state_order[::-1]
            )
            issue_queryset = issue_queryset.annotate(
                state_order=Case(
                    *[
                        When(state__group=state_group, then=Value(i))
                        for i, state_group in enumerate(state_order)
                    ],
                    default=Value(len(state_order)),
                    output_field=CharField(),
                )
            ).order_by("state_order")
        # assignee and label ordering
        elif order_by_param in [
            "labels__name",
            "-labels__name",
            "assignees__first_name",
            "-assignees__first_name",
        ]:
            issue_queryset = issue_queryset.annotate(
                max_values=Max(
                    order_by_param[1::]
                    if order_by_param.startswith("-")
                    else order_by_param
                )
            ).order_by(
                "-max_values" if order_by_param.startswith("-") else "max_values"
            )
        else:
            issue_queryset = issue_queryset.order_by(order_by_param)

        if self.fields or self.expand:
            issues = IssueSerializer(
                queryset, many=True, fields=self.fields, expand=self.expand
            ).data
        else:
            issues = issue_queryset.values(
                "id",
                "name",
                "state_id",
                "sort_order",
                "completed_at",
                "estimate_point",
                "priority",
                "start_date",
                "target_date",
                "sequence_id",
                "project_id",
                "parent_id",
                "cycle_id",
                "module_ids",
                "label_ids",
                "assignee_ids",
                "sub_issues_count",
                "created_at",
                "updated_at",
                "created_by",
                "updated_by",
                "attachment_count",
                "link_count",
                "is_draft",
                "archived_at",
            )
        return Response(issues, status=status.HTTP_200_OK)


class IssueViewSet(BaseViewSet):
    def get_serializer_class(self):
        return (
            IssueCreateSerializer
            if self.action in ["create", "update", "partial_update"]
            else IssueSerializer
        )

    model = Issue
    webhook_event = "issue"
    permission_classes = [
        ProjectEntityPermission,
    ]

    search_fields = [
        "name",
    ]

    filterset_fields = [
        "state__name",
        "assignees__id",
        "workspace__id",
    ]

    def get_queryset(self):
        return (
            Issue.issue_objects.filter(project_id=self.kwargs.get("project_id"))
            .filter(workspace__slug=self.kwargs.get("workspace_slug"))
            .select_related("workspace", "project", "state", "parent")
            .prefetch_related("assignees", "labels", "issue_module__module")
            .annotate(cycle_id=F("issue_cycle__cycle_id"))
            .annotate(
                link_count=IssueLink.objects.filter(issue=OuterRef("id"))
                .order_by()
                .annotate(count=Func(F("id"), function="Count"))
                .values("count")
            )
            .annotate(
                attachment_count=IssueAttachment.objects.filter(issue=OuterRef("id"))
                .order_by()
                .annotate(count=Func(F("id"), function="Count"))
                .values("count")
            )
            .annotate(
                sub_issues_count=Issue.issue_objects.filter(parent=OuterRef("id"))
                .order_by()
                .annotate(count=Func(F("id"), function="Count"))
                .values("count")
            )
            .annotate(
                label_ids=Coalesce(
                    ArrayAgg(
                        "labels__id",
                        distinct=True,
                        filter=~Q(labels__id__isnull=True),
                    ),
                    Value([], output_field=ArrayField(BigIntegerField())),
                ),
                assignee_ids=Coalesce(
                    ArrayAgg(
                        "assignees__id",
                        distinct=True,
                        filter=~Q(assignees__id__isnull=True),
                    ),
                    Value([], output_field=ArrayField(BigIntegerField())),
                ),
                module_ids=Coalesce(
                    ArrayAgg(
                        "issue_module__module_id",
                        distinct=True,
                        filter=~Q(issue_module__module_id__isnull=True),
                    ),
                    Value([], output_field=ArrayField(BigIntegerField())),
                ),
            )
        ).distinct()

    @method_decorator(gzip_page)
    def list(self, request, workspace_slug, project_id):
        filters = issue_filters(request.query_params, "GET")
        order_by_param = request.GET.get("order_by", "-created_at")

        issue_queryset = self.get_queryset().filter(**filters)
        # Custom ordering for priority and state
        priority_order = ["urgent", "high", "medium", "low", "none"]
        state_order = [
            "backlog",
            "unstarted",
            "started",
            "completed",
            "cancelled",
        ]

        # Priority Ordering
        if order_by_param == "priority" or order_by_param == "-priority":
            priority_order = (
                priority_order if order_by_param == "priority" else priority_order[::-1]
            )
            issue_queryset = issue_queryset.annotate(
                priority_order=Case(
                    *[
                        When(priority=p, then=Value(i))
                        for i, p in enumerate(priority_order)
                    ],
                    output_field=CharField(),
                )
            ).order_by("priority_order")

        # State Ordering
        elif order_by_param in [
            "state__name",
            "state__group",
            "-state__name",
            "-state__group",
        ]:
            state_order = (
                state_order
                if order_by_param in ["state__name", "state__group"]
                else state_order[::-1]
            )
            issue_queryset = issue_queryset.annotate(
                state_order=Case(
                    *[
                        When(state__group=state_group, then=Value(i))
                        for i, state_group in enumerate(state_order)
                    ],
                    default=Value(len(state_order)),
                    output_field=CharField(),
                )
            ).order_by("state_order")
        # assignee and label ordering
        elif order_by_param in [
            "labels__name",
            "-labels__name",
            "assignees__first_name",
            "-assignees__first_name",
        ]:
            issue_queryset = issue_queryset.annotate(
                max_values=Max(
                    order_by_param[1::]
                    if order_by_param.startswith("-")
                    else order_by_param
                )
            ).order_by(
                "-max_values" if order_by_param.startswith("-") else "max_values"
            )
        else:
            issue_queryset = issue_queryset.order_by(order_by_param)

        # Only use serializer when expand or fields else return by values
        if self.expand or self.fields:
            issues = IssueSerializer(
                issue_queryset,
                many=True,
                fields=self.fields,
                expand=self.expand,
            ).data
        else:
            issues = issue_queryset.values(
                "id",
                "name",
                "state_id",
                "sort_order",
                "completed_at",
                "estimate_point",
                "priority",
                "start_date",
                "target_date",
                "sequence_id",
                "project_id",
                "parent_id",
                "cycle_id",
                "module_ids",
                "label_ids",
                "assignee_ids",
                "sub_issues_count",
                "created_at",
                "updated_at",
                "created_by",
                "updated_by",
                "attachment_count",
                "link_count",
                "is_draft",
                "archived_at",
            )
        return Response(issues, status=status.HTTP_200_OK)

    def create(self, request, workspace_slug, project_id):
        project = Project.objects.get(pk=project_id)

        serializer = IssueCreateSerializer(
            data=request.data,
            context={
                "project_id": project_id,
                "workspace_id": project.workspace_id,
                "default_assignee_id": project.default_assignee_id,
            },
        )

        if serializer.is_valid():
            serializer.save(
                created_by=self.request.user,
                updated_by=self.request.user,
            )

            # Track the issue
            issue_activity.delay(
                type="issue.activity.created",
                requested_data=json.dumps(self.request.data, cls=DjangoJSONEncoder),
                actor_id=str(request.user.id),
                issue_id=str(serializer.data.get("id", None)),
                project_id=str(project_id),
                current_instance=None,
                epoch=int(timezone.now().timestamp()),
                notification=True,
            )
            issue = (
                self.get_queryset()
                .filter(pk=serializer.data["id"])
                .values(
                    "id",
                    "name",
                    "state_id",
                    "sort_order",
                    "completed_at",
                    "estimate_point",
                    "priority",
                    "start_date",
                    "target_date",
                    "sequence_id",
                    "project_id",
                    "parent_id",
                    "cycle_id",
                    "module_ids",
                    "label_ids",
                    "assignee_ids",
                    "sub_issues_count",
                    "created_at",
                    "updated_at",
                    "created_by",
                    "updated_by",
                    "attachment_count",
                    "link_count",
                    "is_draft",
                    "archived_at",
                )
                .first()
            )
            return Response(issue, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def retrieve(self, request, workspace_slug, project_id, pk=None):
        issue = (
            self.get_queryset()
            .filter(pk=pk)
            .prefetch_related(
                Prefetch(
                    "issue_reactions",
                    queryset=IssueReaction.objects.select_related("issue", "actor"),
                )
            )
            .prefetch_related(
                Prefetch(
                    "issue_attachment",
                    queryset=IssueAttachment.objects.select_related("issue"),
                )
            )
            .prefetch_related(
                Prefetch(
                    "issue_link",
                    queryset=IssueLink.objects.select_related("created_by"),
                )
            )
            .annotate(
                is_subscribed=Exists(
                    IssueSubscriber.objects.filter(
                        workspace__slug=workspace_slug,
                        project_id=project_id,
                        issue_id=OuterRef("pk"),
                        subscriber=request.user,
                    )
                )
            )
        ).first()
        if not issue:
            return Response(
                {"error": "The required object does not exist."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = IssueDetailSerializer(issue, expand=self.expand)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def partial_update(self, request, workspace_slug, project_id, pk=None):
        issue = self.get_queryset().filter(pk=pk).first()

        if not issue:
            return Response(
                {"error": "Issue not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        current_instance = json.dumps(
            IssueSerializer(issue).data, cls=DjangoJSONEncoder
        )

        requested_data = json.dumps(self.request.data, cls=DjangoJSONEncoder)
        serializer = IssueCreateSerializer(issue, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save(
                updated_by=self.request.user,
            )
            issue_activity.delay(
                type="issue.activity.updated",
                requested_data=requested_data,
                actor_id=str(request.user.id),
                issue_id=str(pk),
                project_id=str(project_id),
                current_instance=current_instance,
                epoch=int(timezone.now().timestamp()),
                notification=True,
            )
            issue = self.get_queryset().filter(pk=pk).first()
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, workspace_slug, project_id, pk=None):
        issue = Issue.objects.get(
            workspace__slug=workspace_slug, project_id=project_id, pk=pk
        )
        issue.delete()
        issue_activity.delay(
            type="issue.activity.deleted",
            requested_data=json.dumps({"issue_id": str(pk)}),
            actor_id=str(request.user.id),
            issue_id=str(pk),
            project_id=str(project_id),
            current_instance={},
            epoch=int(timezone.now().timestamp()),
            notification=True,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class IssueActivityEndpoint(BaseAPIView):
    permission_classes = [
        ProjectEntityPermission,
    ]

    @method_decorator(gzip_page)
    def get(self, request, workspace_slug, project_id, issue_id):
        filters = {}
        if request.GET.get("created_at__gt", None) is not None:
            filters = {"created_at__gt": request.GET.get("created_at__gt")}

        issue_activities = (
            IssueActivity.objects.filter(issue_id=issue_id)
            .filter(
                ~Q(field__in=["comment", "vote", "reaction", "draft"]),
                project__project_projectmember__member=self.request.user,
                project__project_projectmember__is_active=True,
                workspace__slug=workspace_slug,
            )
            .filter(**filters)
            .select_related("actor", "workspace", "issue", "project")
        ).order_by("created_at")
        issue_comments = (
            IssueComment.objects.filter(issue_id=issue_id)
            .filter(
                project__project_projectmember__member=self.request.user,
                project__project_projectmember__is_active=True,
                workspace__slug=workspace_slug,
            )
            .filter(**filters)
            .order_by("created_at")
            .select_related("actor", "issue", "project", "workspace")
            .prefetch_related(
                Prefetch(
                    "comment_reactions",
                    queryset=CommentReaction.objects.select_related("actor"),
                )
            )
        )
        issue_activities = IssueActivitySerializer(issue_activities, many=True).data
        issue_comments = IssueCommentSerializer(issue_comments, many=True).data

        if request.GET.get("activity_type", None) == "issue-property":
            return Response(issue_activities, status=status.HTTP_200_OK)

        if request.GET.get("activity_type", None) == "issue-comment":
            return Response(issue_comments, status=status.HTTP_200_OK)

        result_list = sorted(
            chain(issue_activities, issue_comments),
            key=lambda instance: instance["created_at"],
        )

        return Response(result_list, status=status.HTTP_200_OK)


class IssueCommentViewSet(BaseViewSet):
    serializer_class = IssueCommentSerializer
    model = IssueComment
    webhook_event = "issue_comment"
    permission_classes = [
        ProjectLitePermission,
    ]

    filterset_fields = [
        "issue__id",
        "workspace__id",
    ]

    def get_queryset(self):
        return self.filter_queryset(
            super()
            .get_queryset()
            .filter(workspace__slug=self.kwargs.get("workspace_slug"))
            .filter(project_id=self.kwargs.get("project_id"))
            .filter(issue_id=self.kwargs.get("issue_id"))
            .filter(
                project__project_projectmember__member=self.request.user,
                project__project_projectmember__is_active=True,
            )
            .select_related("project")
            .select_related("workspace")
            .select_related("issue")
            .annotate(
                is_member=Exists(
                    ProjectMember.objects.filter(
                        workspace__slug=self.kwargs.get("workspace_slug"),
                        project_id=self.kwargs.get("project_id"),
                        member_id=self.request.user.id,
                        is_active=True,
                    )
                )
            )
            .distinct()
        )

    def create(self, request, workspace_slug, project_id, issue_id):
        serializer = IssueCommentSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(
                project_id=project_id,
                issue_id=issue_id,
                actor=request.user,
                created_by=self.request.user,
                updated_by=self.request.user,
            )
            issue_activity.delay(
                type="comment.activity.created",
                requested_data=json.dumps(serializer.data, cls=DjangoJSONEncoder),
                actor_id=str(self.request.user.id),
                issue_id=str(self.kwargs.get("issue_id")),
                project_id=str(self.kwargs.get("project_id")),
                current_instance=None,
                epoch=int(timezone.now().timestamp()),
                notification=True,
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def partial_update(self, request, workspace_slug, project_id, issue_id, pk):
        issue_comment = IssueComment.objects.get(
            workspace__slug=workspace_slug,
            project_id=project_id,
            issue_id=issue_id,
            pk=pk,
        )
        requested_data = json.dumps(self.request.data, cls=DjangoJSONEncoder)
        current_instance = json.dumps(
            IssueCommentSerializer(issue_comment).data,
            cls=DjangoJSONEncoder,
        )
        serializer = IssueCommentSerializer(
            issue_comment, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save(
                updated_by=self.request.user,
            )
            issue_activity.delay(
                type="comment.activity.updated",
                requested_data=requested_data,
                actor_id=str(request.user.id),
                issue_id=str(issue_id),
                project_id=str(project_id),
                current_instance=current_instance,
                epoch=int(timezone.now().timestamp()),
                notification=True,
            )
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, workspace_slug, project_id, issue_id, pk):
        issue_comment = IssueComment.objects.get(
            workspace__slug=workspace_slug,
            project_id=project_id,
            issue_id=issue_id,
            pk=pk,
        )
        current_instance = json.dumps(
            IssueCommentSerializer(issue_comment).data,
            cls=DjangoJSONEncoder,
        )
        issue_comment.delete()
        issue_activity.delay(
            type="comment.activity.deleted",
            requested_data=json.dumps({"comment_id": str(pk)}),
            actor_id=str(request.user.id),
            issue_id=str(issue_id),
            project_id=str(project_id),
            current_instance=current_instance,
            epoch=int(timezone.now().timestamp()),
            notification=True,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class IssueUserDisplayPropertyEndpoint(BaseAPIView):
    permission_classes = [
        ProjectLitePermission,
    ]

    def patch(self, request, workspace_slug, project_id):
        issue_property = IssueProperty.objects.get(
            user=request.user,
            project_id=project_id,
        )

        issue_property.filters = request.data.get("filters", issue_property.filters)
        issue_property.display_filters = request.data.get(
            "display_filters", issue_property.display_filters
        )
        issue_property.display_properties = request.data.get(
            "display_properties", issue_property.display_properties
        )
        issue_property.save()
        serializer = IssuePropertySerializer(issue_property)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def get(self, request, workspace_slug, project_id):
        issue_property, _ = IssueProperty.objects.get_or_create(
            user=request.user, project_id=project_id
        )
        serializer = IssuePropertySerializer(issue_property)
        return Response(serializer.data, status=status.HTTP_200_OK)


class LabelViewSet(BaseViewSet):
    serializer_class = LabelSerializer
    model = Label
    permission_classes = [
        ProjectMemberPermission,
    ]

    def create(self, request, workspace_slug, project_id):
        try:
            serializer = LabelSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save(
                    project_id=project_id,
                    created_by=self.request.user,
                    updated_by=self.request.user,
                )
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except IntegrityError:
            return Response(
                {"error": "Label with the same name already exists in the project"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    def get_queryset(self):
        return self.filter_queryset(
            super()
            .get_queryset()
            .filter(workspace__slug=self.kwargs.get("workspace_slug"))
            .filter(project_id=self.kwargs.get("project_id"))
            .filter(
                project__project_projectmember__member=self.request.user,
                project__project_projectmember__is_active=True,
            )
            .select_related("project")
            .select_related("workspace")
            .select_related("parent")
            .distinct()
            .order_by("sort_order")
        )


class BulkDeleteIssuesEndpoint(BaseAPIView):
    def delete(self, request, workspace_slug):
        data = request.data
        not_enough_permissions = False
        issue_ids = []
        for project_id in data:
            if (
                not ProjectMember.objects.filter(
                    workspace__slug=workspace_slug,
                    member=request.user,
                    project_id=project_id,
                    is_active=True,
                )
                .exclude(role=ERole.GUEST.value)
                .exists()
            ):
                not_enough_permissions = True
                continue
            issue_ids.extend(data[project_id])

        if not len(issue_ids):
            return Response(
                {"error": "Issue IDs are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        issues = Issue.issue_objects.filter(
            workspace__slug=workspace_slug, pk__in=issue_ids
        )

        total_issues = len(issues)

        issues.delete()

        return Response(
            {"message": f"{total_issues} issues were deleted"},
            status=status.HTTP_200_OK
            if not not_enough_permissions
            else status.HTTP_403_FORBIDDEN,
        )


class SubIssuesEndpoint(BaseAPIView):
    permission_classes = [
        ProjectEntityPermission,
    ]

    @method_decorator(gzip_page)
    def get(self, request, workspace_slug, project_id, issue_id):
        sub_issues = (
            Issue.issue_objects.filter(
                parent_id=issue_id, workspace__slug=workspace_slug
            )
            .select_related("workspace", "project", "state", "parent")
            .prefetch_related("assignees", "labels", "issue_module__module")
            .annotate(cycle_id=F("issue_cycle__cycle_id"))
            .annotate(
                link_count=IssueLink.objects.filter(issue=OuterRef("id"))
                .order_by()
                .annotate(count=Func(F("id"), function="Count"))
                .values("count")
            )
            .annotate(
                attachment_count=IssueAttachment.objects.filter(issue=OuterRef("id"))
                .order_by()
                .annotate(count=Func(F("id"), function="Count"))
                .values("count")
            )
            .annotate(
                sub_issues_count=Issue.issue_objects.filter(parent=OuterRef("id"))
                .order_by()
                .annotate(count=Func(F("id"), function="Count"))
                .values("count")
            )
            .annotate(
                label_ids=Coalesce(
                    ArrayAgg(
                        "labels__id",
                        distinct=True,
                        filter=~Q(labels__id__isnull=True),
                    ),
                    Value([], output_field=ArrayField(BigIntegerField())),
                ),
                assignee_ids=Coalesce(
                    ArrayAgg(
                        "assignees__id",
                        distinct=True,
                        filter=~Q(assignees__id__isnull=True),
                    ),
                    Value([], output_field=ArrayField(BigIntegerField())),
                ),
                module_ids=Coalesce(
                    ArrayAgg(
                        "issue_module__module_id",
                        distinct=True,
                        filter=~Q(issue_module__module_id__isnull=True),
                    ),
                    Value([], output_field=ArrayField(BigIntegerField())),
                ),
            )
            .annotate(state_group=F("state__group"))
        )

        # create's a dict with state group name with their respective issue id's
        result = defaultdict(list)
        for sub_issue in sub_issues:
            result[sub_issue.state_group].append(str(sub_issue.id))

        sub_issues = sub_issues.values(
            "id",
            "name",
            "state_id",
            "sort_order",
            "completed_at",
            "estimate_point",
            "priority",
            "start_date",
            "target_date",
            "sequence_id",
            "project_id",
            "parent_id",
            "cycle_id",
            "module_ids",
            "label_ids",
            "assignee_ids",
            "sub_issues_count",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "attachment_count",
            "link_count",
            "is_draft",
            "archived_at",
        )
        return Response(
            {
                "sub_issues": sub_issues,
                "state_distribution": result,
            },
            status=status.HTTP_200_OK,
        )

    # Assign multiple sub issues
    def post(self, request, workspace_slug, project_id, issue_id):
        parent_issue = Issue.issue_objects.get(pk=issue_id)
        sub_issue_ids = request.data.get("sub_issue_ids", [])

        if not len(sub_issue_ids):
            return Response(
                {"error": "Sub Issue IDs are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sub_issues = Issue.issue_objects.filter(id__in=sub_issue_ids)

        for sub_issue in sub_issues:
            sub_issue.parent = parent_issue

        _ = Issue.objects.bulk_update(sub_issues, ["parent"], batch_size=10)

        updated_sub_issues = Issue.issue_objects.filter(id__in=sub_issue_ids).annotate(
            state_group=F("state__group")
        )

        # Track the issue
        _ = [
            issue_activity.delay(
                type="issue.activity.updated",
                requested_data=json.dumps({"parent": str(issue_id)}),
                actor_id=str(request.user.id),
                issue_id=str(sub_issue_id),
                project_id=str(project_id),
                current_instance=json.dumps({"parent": str(sub_issue_id)}),
                epoch=int(timezone.now().timestamp()),
                notification=True,
            )
            for sub_issue_id in sub_issue_ids
        ]

        # create's a dict with state group name with their respective issue id's
        result = defaultdict(list)
        for sub_issue in updated_sub_issues:
            result[sub_issue.state_group].append(str(sub_issue.id))

        serializer = IssueSerializer(
            updated_sub_issues,
            many=True,
        )
        return Response(
            {
                "sub_issues": serializer.data,
                "state_distribution": result,
            },
            status=status.HTTP_200_OK,
        )


class IssueLinkViewSet(BaseViewSet):
    permission_classes = [
        ProjectEntityPermission,
    ]

    model = IssueLink
    serializer_class = IssueLinkSerializer

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(workspace__slug=self.kwargs.get("workspace_slug"))
            .filter(project_id=self.kwargs.get("project_id"))
            .filter(issue_id=self.kwargs.get("issue_id"))
            .filter(
                project__project_projectmember__member=self.request.user,
                project__project_projectmember__is_active=True,
            )
            .order_by("-created_at")
            .distinct()
        )

    def create(self, request, workspace_slug, project_id, issue_id):
        serializer = IssueLinkSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(
                project_id=project_id,
                issue_id=issue_id,
                created_by=self.request.user,
                updated_by=self.request.user,
            )
            issue_activity.delay(
                type="link.activity.created",
                requested_data=json.dumps(serializer.data, cls=DjangoJSONEncoder),
                actor_id=str(self.request.user.id),
                issue_id=str(self.kwargs.get("issue_id")),
                project_id=str(self.kwargs.get("project_id")),
                current_instance=None,
                epoch=int(timezone.now().timestamp()),
                notification=True,
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def partial_update(self, request, workspace_slug, project_id, issue_id, pk):
        issue_link = IssueLink.objects.get(
            workspace__slug=workspace_slug,
            project_id=project_id,
            issue_id=issue_id,
            pk=pk,
        )
        requested_data = json.dumps(request.data, cls=DjangoJSONEncoder)
        current_instance = json.dumps(
            IssueLinkSerializer(issue_link).data,
            cls=DjangoJSONEncoder,
        )
        serializer = IssueLinkSerializer(issue_link, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            issue_activity.delay(
                type="link.activity.updated",
                requested_data=requested_data,
                actor_id=str(request.user.id),
                issue_id=str(issue_id),
                project_id=str(project_id),
                current_instance=current_instance,
                epoch=int(timezone.now().timestamp()),
                notification=True,
            )
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, workspace_slug, project_id, issue_id, pk):
        issue_link = IssueLink.objects.get(
            workspace__slug=workspace_slug,
            project_id=project_id,
            issue_id=issue_id,
            pk=pk,
        )
        current_instance = json.dumps(
            IssueLinkSerializer(issue_link).data,
            cls=DjangoJSONEncoder,
        )
        issue_activity.delay(
            type="link.activity.deleted",
            requested_data=json.dumps({"link_id": str(pk)}),
            actor_id=str(request.user.id),
            issue_id=str(issue_id),
            project_id=str(project_id),
            current_instance=current_instance,
            epoch=int(timezone.now().timestamp()),
            notification=True,
        )
        issue_link.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BulkCreateIssueLabelsEndpoint(BaseAPIView):
    def post(self, request, workspace_slug, project_id):
        label_data = request.data.get("label_data", [])
        project = Project.objects.get(pk=project_id)

        labels = Label.objects.bulk_create(
            [
                Label(
                    name=label.get("name", "Migrated"),
                    description=label.get("description", "Migrated Issue"),
                    color="#" + "%06x" % random.randint(0, 0xFFFFFF),
                    project_id=project_id,
                    workspace_id=project.workspace_id,
                    created_by=request.user,
                    updated_by=request.user,
                )
                for label in label_data
            ],
            batch_size=50,
            ignore_conflicts=True,
        )

        return Response(
            {"labels": LabelSerializer(labels, many=True).data},
            status=status.HTTP_201_CREATED,
        )


class IssueAttachmentEndpoint(BaseAPIView):
    serializer_class = IssueAttachmentSerializer
    permission_classes = [
        ProjectEntityPermission,
    ]
    model = IssueAttachment
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, workspace_slug, project_id, issue_id):
        serializer = IssueAttachmentSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(
                project_id=project_id,
                issue_id=issue_id,
                created_by=self.request.user,
                updated_by=self.request.user,
            )
            issue_activity.delay(
                type="attachment.activity.created",
                requested_data=None,
                actor_id=str(self.request.user.id),
                issue_id=str(self.kwargs.get("issue_id", None)),
                project_id=str(self.kwargs.get("project_id", None)),
                current_instance=json.dumps(
                    serializer.data,
                    cls=DjangoJSONEncoder,
                ),
                epoch=int(timezone.now().timestamp()),
                notification=True,
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, workspace_slug, project_id, issue_id, pk):
        issue_attachment = IssueAttachment.objects.get(pk=pk)
        issue_attachment.asset.delete(save=False)
        issue_attachment.delete()
        issue_activity.delay(
            type="attachment.activity.deleted",
            requested_data=None,
            actor_id=str(self.request.user.id),
            issue_id=str(self.kwargs.get("issue_id", None)),
            project_id=str(self.kwargs.get("project_id", None)),
            current_instance=None,
            epoch=int(timezone.now().timestamp()),
            notification=True,
        )

        return Response(status=status.HTTP_204_NO_CONTENT)

    def get(self, request, workspace_slug, project_id, issue_id):
        issue_attachments = IssueAttachment.objects.filter(
            issue_id=issue_id, workspace__slug=workspace_slug, project_id=project_id
        )
        serializer = IssueAttachmentSerializer(issue_attachments, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class IssueArchiveViewSet(BaseViewSet):
    permission_classes = [
        ProjectEntityPermission,
    ]
    serializer_class = IssueFlatSerializer
    model = Issue

    def get_queryset(self):
        return (
            Issue.objects.annotate(
                sub_issues_count=Issue.objects.filter(parent=OuterRef("id"))
                .order_by()
                .annotate(count=Func(F("id"), function="Count"))
                .values("count")
            )
            .filter(archived_at__isnull=False)
            .filter(project_id=self.kwargs.get("project_id"))
            .filter(workspace__slug=self.kwargs.get("workspace_slug"))
            .select_related("workspace", "project", "state", "parent")
            .prefetch_related("assignees", "labels", "issue_module__module")
            .annotate(cycle_id=F("issue_cycle__cycle_id"))
            .annotate(
                link_count=IssueLink.objects.filter(issue=OuterRef("id"))
                .order_by()
                .annotate(count=Func(F("id"), function="Count"))
                .values("count")
            )
            .annotate(
                attachment_count=IssueAttachment.objects.filter(issue=OuterRef("id"))
                .order_by()
                .annotate(count=Func(F("id"), function="Count"))
                .values("count")
            )
            .annotate(
                sub_issues_count=Issue.issue_objects.filter(parent=OuterRef("id"))
                .order_by()
                .annotate(count=Func(F("id"), function="Count"))
                .values("count")
            )
            .annotate(
                label_ids=Coalesce(
                    ArrayAgg(
                        "labels__id",
                        distinct=True,
                        filter=~Q(labels__id__isnull=True),
                    ),
                    Value([], output_field=ArrayField(BigIntegerField())),
                ),
                assignee_ids=Coalesce(
                    ArrayAgg(
                        "assignees__id",
                        distinct=True,
                        filter=~Q(assignees__id__isnull=True),
                    ),
                    Value([], output_field=ArrayField(BigIntegerField())),
                ),
                module_ids=Coalesce(
                    ArrayAgg(
                        "issue_module__module_id",
                        distinct=True,
                        filter=~Q(issue_module__module_id__isnull=True),
                    ),
                    Value([], output_field=ArrayField(BigIntegerField())),
                ),
            )
        )

    @method_decorator(gzip_page)
    def list(self, request, workspace_slug, project_id):
        filters = issue_filters(request.query_params, "GET")
        show_sub_issues = request.GET.get("show_sub_issues", "true")

        # Custom ordering for priority and state
        priority_order = ["urgent", "high", "medium", "low", "none"]
        state_order = [
            "backlog",
            "unstarted",
            "started",
            "completed",
            "cancelled",
        ]

        order_by_param = request.GET.get("order_by", "-created_at")

        issue_queryset = self.get_queryset().filter(**filters)

        # Priority Ordering
        if order_by_param == "priority" or order_by_param == "-priority":
            priority_order = (
                priority_order if order_by_param == "priority" else priority_order[::-1]
            )
            issue_queryset = issue_queryset.annotate(
                priority_order=Case(
                    *[
                        When(priority=p, then=Value(i))
                        for i, p in enumerate(priority_order)
                    ],
                    output_field=CharField(),
                )
            ).order_by("priority_order")

        # State Ordering
        elif order_by_param in [
            "state__name",
            "state__group",
            "-state__name",
            "-state__group",
        ]:
            state_order = (
                state_order
                if order_by_param in ["state__name", "state__group"]
                else state_order[::-1]
            )
            issue_queryset = issue_queryset.annotate(
                state_order=Case(
                    *[
                        When(state__group=state_group, then=Value(i))
                        for i, state_group in enumerate(state_order)
                    ],
                    default=Value(len(state_order)),
                    output_field=CharField(),
                )
            ).order_by("state_order")
        # assignee and label ordering
        elif order_by_param in [
            "labels__name",
            "-labels__name",
            "assignees__first_name",
            "-assignees__first_name",
        ]:
            issue_queryset = issue_queryset.annotate(
                max_values=Max(
                    order_by_param[1::]
                    if order_by_param.startswith("-")
                    else order_by_param
                )
            ).order_by(
                "-max_values" if order_by_param.startswith("-") else "max_values"
            )
        else:
            issue_queryset = issue_queryset.order_by(order_by_param)

        issue_queryset = (
            issue_queryset
            if show_sub_issues == "true"
            else issue_queryset.filter(parent__isnull=True)
        )
        if self.expand or self.fields:
            issues = IssueSerializer(
                issue_queryset,
                many=True,
                fields=self.fields,
            ).data
        else:
            issues = issue_queryset.values(
                "id",
                "name",
                "state_id",
                "sort_order",
                "completed_at",
                "estimate_point",
                "priority",
                "start_date",
                "target_date",
                "sequence_id",
                "project_id",
                "parent_id",
                "cycle_id",
                "module_ids",
                "label_ids",
                "assignee_ids",
                "sub_issues_count",
                "created_at",
                "updated_at",
                "created_by",
                "updated_by",
                "attachment_count",
                "link_count",
                "is_draft",
                "archived_at",
            )
        return Response(issues, status=status.HTTP_200_OK)

    def retrieve(self, request, workspace_slug, project_id, pk=None):
        issue = (
            self.get_queryset()
            .filter(pk=pk)
            .prefetch_related(
                Prefetch(
                    "issue_reactions",
                    queryset=IssueReaction.objects.select_related("issue", "actor"),
                )
            )
            .prefetch_related(
                Prefetch(
                    "issue_attachment",
                    queryset=IssueAttachment.objects.select_related("issue"),
                )
            )
            .prefetch_related(
                Prefetch(
                    "issue_link",
                    queryset=IssueLink.objects.select_related("created_by"),
                )
            )
            .annotate(
                is_subscribed=Exists(
                    IssueSubscriber.objects.filter(
                        workspace__slug=workspace_slug,
                        project_id=project_id,
                        issue_id=OuterRef("pk"),
                        subscriber=request.user,
                    )
                )
            )
        ).first()
        if not issue:
            return Response(
                {"error": "The required object does not exist."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = IssueDetailSerializer(issue, expand=self.expand)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def archive(self, request, workspace_slug, project_id, pk=None):
        issue = Issue.issue_objects.get(
            workspace__slug=workspace_slug,
            project_id=project_id,
            pk=pk,
        )
        if issue.state.group not in ["completed", "cancelled"]:
            return Response(
                {"error": "Can only archive completed or cancelled state group issue"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        issue_activity.delay(
            type="issue.activity.updated",
            requested_data=json.dumps(
                {"archived_at": str(timezone.now().date()), "automation": False}
            ),
            actor_id=str(request.user.id),
            issue_id=str(issue.id),
            project_id=str(project_id),
            current_instance=json.dumps(
                IssueSerializer(issue).data, cls=DjangoJSONEncoder
            ),
            epoch=int(timezone.now().timestamp()),
            notification=True,
        )
        issue.archived_at = timezone.now().date()
        issue.save()

        return Response(
            {"archived_at": str(issue.archived_at)}, status=status.HTTP_200_OK
        )

    def unarchive(self, request, workspace_slug, project_id, pk=None):
        issue = Issue.objects.get(
            workspace__slug=workspace_slug,
            project_id=project_id,
            archived_at__isnull=False,
            pk=pk,
        )
        issue_activity.delay(
            type="issue.activity.updated",
            requested_data=json.dumps({"archived_at": None}),
            actor_id=str(request.user.id),
            issue_id=str(issue.id),
            project_id=str(project_id),
            current_instance=json.dumps(
                IssueSerializer(issue).data, cls=DjangoJSONEncoder
            ),
            epoch=int(timezone.now().timestamp()),
            notification=True,
        )
        issue.archived_at = None
        issue.save()

        return Response(status=status.HTTP_204_NO_CONTENT)


class IssueSubscriberViewSet(BaseViewSet):
    serializer_class = IssueSubscriberSerializer
    model = IssueSubscriber

    permission_classes = [
        ProjectEntityPermission,
    ]

    def get_permissions(self):
        if self.action in ["subscribe", "unsubscribe", "subscription_status"]:
            self.permission_classes = [
                ProjectLitePermission,
            ]
        else:
            self.permission_classes = [
                ProjectEntityPermission,
            ]

        return super(IssueSubscriberViewSet, self).get_permissions()

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(workspace__slug=self.kwargs.get("workspace_slug"))
            .filter(project_id=self.kwargs.get("project_id"))
            .filter(issue_id=self.kwargs.get("issue_id"))
            .filter(
                project__project_projectmember__member=self.request.user,
                project__project_projectmember__is_active=True,
            )
            .order_by("-created_at")
            .distinct()
        )

    def subscribe(self, request, workspace_slug, project_id, issue_id):
        if IssueSubscriber.objects.filter(
            issue_id=issue_id,
            subscriber=request.user,
            workspace__slug=workspace_slug,
            project=project_id,
        ).exists():
            return Response(
                {"message": "User already subscribed to the issue."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        subscriber = IssueSubscriber.objects.create(
            issue_id=issue_id,
            subscriber_id=request.user.id,
            project_id=project_id,
            created_by=request.user,
            updated_by=request.user,
        )
        serializer = IssueSubscriberSerializer(subscriber)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def unsubscribe(self, request, workspace_slug, project_id, issue_id):
        issue_subscriber = IssueSubscriber.objects.get(
            project=project_id,
            subscriber=request.user,
            workspace__slug=workspace_slug,
            issue=issue_id,
        )
        issue_subscriber.delete()
        return Response(
            status=status.HTTP_204_NO_CONTENT,
        )

    def subscription_status(self, request, workspace_slug, project_id, issue_id):
        issue_subscriber = IssueSubscriber.objects.filter(
            issue=issue_id,
            subscriber=request.user,
            workspace__slug=workspace_slug,
            project=project_id,
        ).exists()
        return Response({"subscribed": issue_subscriber}, status=status.HTTP_200_OK)


class IssueReactionViewSet(BaseViewSet):
    serializer_class = IssueReactionSerializer
    model = IssueReaction
    permission_classes = [
        ProjectLitePermission,
    ]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(workspace__slug=self.kwargs.get("workspace_slug"))
            .filter(project_id=self.kwargs.get("project_id"))
            .filter(issue_id=self.kwargs.get("issue_id"))
            .filter(
                project__project_projectmember__member=self.request.user,
                project__project_projectmember__is_active=True,
            )
            .order_by("-created_at")
            .distinct()
        )

    def create(self, request, workspace_slug, project_id, issue_id):
        serializer = IssueReactionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(
                issue_id=issue_id,
                project_id=project_id,
                created_by=self.request.user,
                updated_by=self.request.user,
                actor=request.user,
            )
            issue_activity.delay(
                type="issue_reaction.activity.created",
                requested_data=json.dumps(request.data, cls=DjangoJSONEncoder),
                actor_id=str(request.user.id),
                issue_id=str(issue_id),
                project_id=str(project_id),
                current_instance=None,
                epoch=int(timezone.now().timestamp()),
                notification=True,
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, workspace_slug, project_id, issue_id, reaction_code):
        issue_reaction = IssueReaction.objects.get(
            workspace__slug=workspace_slug,
            project_id=project_id,
            issue_id=issue_id,
            reaction=reaction_code,
            actor=request.user,
        )
        issue_activity.delay(
            type="issue_reaction.activity.deleted",
            requested_data=None,
            actor_id=str(self.request.user.id),
            issue_id=str(self.kwargs.get("issue_id", None)),
            project_id=str(self.kwargs.get("project_id", None)),
            current_instance=json.dumps(
                {
                    "reaction": str(reaction_code),
                    "identifier": str(issue_reaction.id),
                }
            ),
            epoch=int(timezone.now().timestamp()),
            notification=True,
        )
        issue_reaction.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CommentReactionViewSet(BaseViewSet):
    serializer_class = CommentReactionSerializer
    model = CommentReaction
    permission_classes = [
        ProjectLitePermission,
    ]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(workspace__slug=self.kwargs.get("workspace_slug"))
            .filter(project_id=self.kwargs.get("project_id"))
            .filter(comment_id=self.kwargs.get("comment_id"))
            .filter(
                project__project_projectmember__member=self.request.user,
                project__project_projectmember__is_active=True,
            )
            .order_by("-created_at")
            .distinct()
        )

    def create(self, request, workspace_slug, project_id, comment_id):
        serializer = CommentReactionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(
                project_id=project_id,
                created_by=self.request.user,
                updated_by=self.request.user,
                actor_id=request.user.id,
                comment_id=comment_id,
            )
            issue_activity.delay(
                type="comment_reaction.activity.created",
                requested_data=json.dumps(request.data, cls=DjangoJSONEncoder),
                actor_id=str(request.user.id),
                issue_id=None,
                project_id=str(project_id),
                current_instance=None,
                epoch=int(timezone.now().timestamp()),
                notification=True,
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, workspace_slug, project_id, comment_id, reaction_code):
        comment_reaction = CommentReaction.objects.get(
            workspace__slug=workspace_slug,
            project_id=project_id,
            comment_id=comment_id,
            reaction=reaction_code,
            actor=request.user,
        )
        issue_activity.delay(
            type="comment_reaction.activity.deleted",
            requested_data=None,
            actor_id=str(self.request.user.id),
            issue_id=None,
            project_id=str(self.kwargs.get("project_id", None)),
            current_instance=json.dumps(
                {
                    "reaction": str(reaction_code),
                    "identifier": str(comment_reaction.id),
                    "comment_id": str(comment_id),
                }
            ),
            epoch=int(timezone.now().timestamp()),
            notification=True,
        )
        comment_reaction.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class IssueRelationViewSet(BaseViewSet):
    serializer_class = IssueRelationSerializer
    model = IssueRelation
    permission_classes = [
        ProjectEntityPermission,
    ]

    def get_queryset(self):
        return self.filter_queryset(
            super()
            .get_queryset()
            .filter(workspace__slug=self.kwargs.get("workspace_slug"))
            .filter(project_id=self.kwargs.get("project_id"))
            .filter(issue_id=self.kwargs.get("issue_id"))
            .filter(
                project__project_projectmember__member=self.request.user,
                project__project_projectmember__is_active=True,
            )
            .select_related("project")
            .select_related("workspace")
            .select_related("issue")
            .distinct()
        )

    def list(self, request, workspace_slug, project_id, issue_id):
        issue_relations = (
            IssueRelation.objects.filter(
                Q(issue_id=issue_id) | Q(related_issue=issue_id)
            )
            .filter(workspace__slug=self.kwargs.get("workspace_slug"))
            .select_related("project")
            .select_related("workspace")
            .select_related("issue")
            .order_by("-created_at")
            .distinct()
        )

        blocking_issues = issue_relations.filter(
            relation_type="blocked_by", related_issue_id=issue_id
        )
        blocked_by_issues = issue_relations.filter(
            relation_type="blocked_by", issue_id=issue_id
        )
        duplicate_issues = issue_relations.filter(
            issue_id=issue_id, relation_type="duplicate"
        )
        duplicate_issues_related = issue_relations.filter(
            related_issue_id=issue_id, relation_type="duplicate"
        )
        relates_to_issues = issue_relations.filter(
            issue_id=issue_id, relation_type="relates_to"
        )
        relates_to_issues_related = issue_relations.filter(
            related_issue_id=issue_id, relation_type="relates_to"
        )

        blocked_by_issues_serialized = IssueRelationSerializer(
            blocked_by_issues, many=True
        ).data
        duplicate_issues_serialized = IssueRelationSerializer(
            duplicate_issues, many=True
        ).data
        relates_to_issues_serialized = IssueRelationSerializer(
            relates_to_issues, many=True
        ).data

        # revere relation for blocked by issues
        blocking_issues_serialized = RelatedIssueSerializer(
            blocking_issues, many=True
        ).data
        # reverse relation for duplicate issues
        duplicate_issues_related_serialized = RelatedIssueSerializer(
            duplicate_issues_related, many=True
        ).data
        # reverse relation for related issues
        relates_to_issues_related_serialized = RelatedIssueSerializer(
            relates_to_issues_related, many=True
        ).data

        response_data = {
            "blocking": blocking_issues_serialized,
            "blocked_by": blocked_by_issues_serialized,
            "duplicate": duplicate_issues_serialized
            + duplicate_issues_related_serialized,
            "relates_to": relates_to_issues_serialized
            + relates_to_issues_related_serialized,
        }

        return Response(response_data, status=status.HTTP_200_OK)

    def create(self, request, workspace_slug, project_id, issue_id):
        relation_type = request.data.get("relation_type", None)
        issues = request.data.get("issues", [])
        project = Project.objects.get(pk=project_id)

        issue_relation = IssueRelation.objects.bulk_create(
            [
                IssueRelation(
                    issue_id=(issue if relation_type == "blocking" else issue_id),
                    related_issue_id=(
                        issue_id if relation_type == "blocking" else issue
                    ),
                    relation_type=(
                        "blocked_by" if relation_type == "blocking" else relation_type
                    ),
                    project_id=project_id,
                    workspace_id=project.workspace_id,
                    created_by=request.user,
                    updated_by=request.user,
                )
                for issue in issues
            ],
            batch_size=10,
            ignore_conflicts=True,
        )

        issue_activity.delay(
            type="issue_relation.activity.created",
            requested_data=json.dumps(request.data, cls=DjangoJSONEncoder),
            actor_id=str(request.user.id),
            issue_id=str(issue_id),
            project_id=str(project_id),
            current_instance=None,
            epoch=int(timezone.now().timestamp()),
            notification=True,
        )

        if relation_type == "blocking":
            return Response(
                RelatedIssueSerializer(issue_relation, many=True).data,
                status=status.HTTP_201_CREATED,
            )
        else:
            return Response(
                IssueRelationSerializer(issue_relation, many=True).data,
                status=status.HTTP_201_CREATED,
            )

    def remove_relation(self, request, workspace_slug, project_id, issue_id):
        relation_type = request.data.get("relation_type", None)
        related_issue = request.data.get("related_issue", None)

        if relation_type == "blocking":
            issue_relation = IssueRelation.objects.get(
                workspace__slug=workspace_slug,
                project_id=project_id,
                issue_id=related_issue,
                related_issue_id=issue_id,
            )
        else:
            issue_relation = IssueRelation.objects.get(
                workspace__slug=workspace_slug,
                project_id=project_id,
                issue_id=issue_id,
                related_issue_id=related_issue,
            )
        current_instance = json.dumps(
            IssueRelationSerializer(issue_relation).data,
            cls=DjangoJSONEncoder,
        )
        issue_relation.delete()
        issue_activity.delay(
            type="issue_relation.activity.deleted",
            requested_data=json.dumps(request.data, cls=DjangoJSONEncoder),
            actor_id=str(request.user.id),
            issue_id=str(issue_id),
            project_id=str(project_id),
            current_instance=current_instance,
            epoch=int(timezone.now().timestamp()),
            notification=True,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class IssueDraftViewSet(BaseViewSet):
    permission_classes = [
        ProjectEntityPermission,
    ]
    serializer_class = IssueFlatSerializer
    model = Issue

    def get_queryset(self):
        return (
            Issue.objects.filter(project_id=self.kwargs.get("project_id"))
            .filter(workspace__slug=self.kwargs.get("workspace_slug"))
            .filter(is_draft=True)
            .select_related("workspace", "project", "state", "parent")
            .prefetch_related("assignees", "labels", "issue_module__module")
            .annotate(cycle_id=F("issue_cycle__cycle_id"))
            .annotate(
                link_count=IssueLink.objects.filter(issue=OuterRef("id"))
                .order_by()
                .annotate(count=Func(F("id"), function="Count"))
                .values("count")
            )
            .annotate(
                attachment_count=IssueAttachment.objects.filter(issue=OuterRef("id"))
                .order_by()
                .annotate(count=Func(F("id"), function="Count"))
                .values("count")
            )
            .annotate(
                sub_issues_count=Issue.issue_objects.filter(parent=OuterRef("id"))
                .order_by()
                .annotate(count=Func(F("id"), function="Count"))
                .values("count")
            )
            .annotate(
                label_ids=Coalesce(
                    ArrayAgg(
                        "labels__id",
                        distinct=True,
                        filter=~Q(labels__id__isnull=True),
                    ),
                    Value([], output_field=ArrayField(BigIntegerField())),
                ),
                assignee_ids=Coalesce(
                    ArrayAgg(
                        "assignees__id",
                        distinct=True,
                        filter=~Q(assignees__id__isnull=True),
                    ),
                    Value([], output_field=ArrayField(BigIntegerField())),
                ),
                module_ids=Coalesce(
                    ArrayAgg(
                        "issue_module__module_id",
                        distinct=True,
                        filter=~Q(issue_module__module_id__isnull=True),
                    ),
                    Value([], output_field=ArrayField(BigIntegerField())),
                ),
            )
        ).distinct()

    @method_decorator(gzip_page)
    def list(self, request, workspace_slug, project_id):
        filters = issue_filters(request.query_params, "GET")
        fields = [field for field in request.GET.get("fields", "").split(",") if field]

        # Custom ordering for priority and state
        priority_order = ["urgent", "high", "medium", "low", "none"]
        state_order = [
            "backlog",
            "unstarted",
            "started",
            "completed",
            "cancelled",
        ]

        order_by_param = request.GET.get("order_by", "-created_at")

        issue_queryset = self.get_queryset().filter(**filters)

        # Priority Ordering
        if order_by_param == "priority" or order_by_param == "-priority":
            priority_order = (
                priority_order if order_by_param == "priority" else priority_order[::-1]
            )
            issue_queryset = issue_queryset.annotate(
                priority_order=Case(
                    *[
                        When(priority=p, then=Value(i))
                        for i, p in enumerate(priority_order)
                    ],
                    output_field=CharField(),
                )
            ).order_by("priority_order")

        # State Ordering
        elif order_by_param in [
            "state__name",
            "state__group",
            "-state__name",
            "-state__group",
        ]:
            state_order = (
                state_order
                if order_by_param in ["state__name", "state__group"]
                else state_order[::-1]
            )
            issue_queryset = issue_queryset.annotate(
                state_order=Case(
                    *[
                        When(state__group=state_group, then=Value(i))
                        for i, state_group in enumerate(state_order)
                    ],
                    default=Value(len(state_order)),
                    output_field=CharField(),
                )
            ).order_by("state_order")
        # assignee and label ordering
        elif order_by_param in [
            "labels__name",
            "-labels__name",
            "assignees__first_name",
            "-assignees__first_name",
        ]:
            issue_queryset = issue_queryset.annotate(
                max_values=Max(
                    order_by_param[1::]
                    if order_by_param.startswith("-")
                    else order_by_param
                )
            ).order_by(
                "-max_values" if order_by_param.startswith("-") else "max_values"
            )
        else:
            issue_queryset = issue_queryset.order_by(order_by_param)

        # Only use serializer when expand else return by values
        if self.expand or self.fields:
            issues = IssueSerializer(
                issue_queryset,
                many=True,
                fields=self.fields,
                expand=self.expand,
            ).data
        else:
            issues = issue_queryset.values(
                "id",
                "name",
                "state_id",
                "sort_order",
                "completed_at",
                "estimate_point",
                "priority",
                "start_date",
                "target_date",
                "sequence_id",
                "project_id",
                "parent_id",
                "cycle_id",
                "module_ids",
                "label_ids",
                "assignee_ids",
                "sub_issues_count",
                "created_at",
                "updated_at",
                "created_by",
                "updated_by",
                "attachment_count",
                "link_count",
                "is_draft",
                "archived_at",
            )
        return Response(issues, status=status.HTTP_200_OK)

    def create(self, request, workspace_slug, project_id):
        project = Project.objects.get(pk=project_id)

        serializer = IssueCreateSerializer(
            data=request.data,
            context={
                "project_id": project_id,
                "workspace_id": project.workspace_id,
                "default_assignee_id": project.default_assignee_id,
            },
        )

        if serializer.is_valid():
            serializer.save(
                is_draft=True,
                created_by=self.request.user,
                updated_by=self.request.user,
            )

            # Track the issue
            issue_activity.delay(
                type="issue_draft.activity.created",
                requested_data=json.dumps(self.request.data, cls=DjangoJSONEncoder),
                actor_id=str(request.user.id),
                issue_id=str(serializer.data.get("id", None)),
                project_id=str(project_id),
                current_instance=None,
                epoch=int(timezone.now().timestamp()),
                notification=True,
            )
            issue = self.get_queryset().filter(pk=serializer.data["id"]).first()
            return Response(IssueSerializer(issue).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def partial_update(self, request, workspace_slug, project_id, pk):
        issue = self.get_queryset().filter(pk=pk).first()

        if not issue:
            return Response(
                {"error": "Issue does not exist"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = IssueCreateSerializer(issue, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            issue_activity.delay(
                type="issue_draft.activity.updated",
                requested_data=json.dumps(request.data, cls=DjangoJSONEncoder),
                actor_id=str(self.request.user.id),
                issue_id=str(self.kwargs.get("pk", None)),
                project_id=str(self.kwargs.get("project_id", None)),
                current_instance=json.dumps(
                    IssueSerializer(issue).data,
                    cls=DjangoJSONEncoder,
                ),
                epoch=int(timezone.now().timestamp()),
                notification=True,
            )
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def retrieve(self, request, workspace_slug, project_id, pk=None):
        issue = (
            self.get_queryset()
            .filter(pk=pk)
            .prefetch_related(
                Prefetch(
                    "issue_reactions",
                    queryset=IssueReaction.objects.select_related("issue", "actor"),
                )
            )
            .prefetch_related(
                Prefetch(
                    "issue_attachment",
                    queryset=IssueAttachment.objects.select_related("issue"),
                )
            )
            .prefetch_related(
                Prefetch(
                    "issue_link",
                    queryset=IssueLink.objects.select_related("created_by"),
                )
            )
            .annotate(
                is_subscribed=Exists(
                    IssueSubscriber.objects.filter(
                        workspace__slug=workspace_slug,
                        project_id=project_id,
                        issue_id=OuterRef("pk"),
                        subscriber=request.user,
                    )
                )
            )
        ).first()

        if not issue:
            return Response(
                {"error": "The required object does not exist."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = IssueDetailSerializer(issue, expand=self.expand)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def destroy(self, request, workspace_slug, project_id, pk=None):
        issue = Issue.objects.get(
            workspace__slug=workspace_slug, project_id=project_id, pk=pk
        )
        issue.delete()
        issue_activity.delay(
            type="issue_draft.activity.deleted",
            requested_data=json.dumps({"issue_id": str(pk)}),
            actor_id=str(request.user.id),
            issue_id=str(pk),
            project_id=str(project_id),
            current_instance={},
            epoch=int(timezone.now().timestamp()),
            notification=True,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
