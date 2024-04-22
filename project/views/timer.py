from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from common.permissions import ProjectMemberPermission
from common.responses import error_response
from common.views import BaseViewSet
from iam.enums import ERole
from iam.models import WorkspaceMember
from project.models import Issue, TrackedTime, TrackedTimeAttachment
from project.serializers import TrackedTimeAttachmentSerializer, TrackedTimeSerializer


class TrackedTimeViewSet(BaseViewSet):
    """
    TrackedTimeViewSet (viewset): To handle all the tracked time related operations
    """

    permission_classes = [ProjectMemberPermission]
    serializer_class = TrackedTimeSerializer
    queryset = TrackedTime.objects.all()

    def create(self, request, workspace_slug, project_id, issue_id, *args, **kwargs):
        """
        create (method): To create a new tracked time record
        """
        if TrackedTime.objects.filter(
            workspace__slug=workspace_slug,
            created_by=request.user,
            end_time__isnull=True,
        ).exists():
            return error_response("Timer is already running for this user", status=400)
        try:
            issue = Issue.objects.get(
                archived_at__isnull=True,
                is_draft=False,
                id=issue_id,
                project_id=project_id,
                workspace__slug=workspace_slug,
            )
        except Issue.DoesNotExist:
            raise PermissionDenied("Issue not found")
        tracked_time = TrackedTime.objects.create(
            description=request.data.get("description", ""),
            is_billable=request.data.get("is_billable", True),
            issue_id=issue_id,
            project_id=project_id,
            workspace=issue.workspace,
            created_by=request.user,
            updated_by=request.user,
            start_time=timezone.now(),
            end_time=None,
            is_approved=False,
        )
        return Response(
            TrackedTimeSerializer(tracked_time).data,
            status=201,
        )

    def list(self, request, workspace_slug, *args, **kwargs):
        """
        list (method): To list all the tracked time records
        """
        isWorkspaceAdmin = WorkspaceMember.objects.filter(
            workspace__slug=workspace_slug,
            member=request.user,
            is_active=True,
            role__gte=ERole.ADMIN.value,
        ).exists()
        project_id = request.query_params.get("project_id")
        issue_id = request.query_params.get("issue_id")
        query = Q(
            workspace__slug=workspace_slug,
            end_time__isnull=False,
        )
        if project_id:
            query = query & Q(project_id=int(project_id))
        if issue_id:
            query = query & Q(issue_id=int(issue_id))
        if not isWorkspaceAdmin:
            query = query & Q(created_by=request.user)
        timeEntries = TrackedTime.objects.filter(query).order_by("-start_time")
        return Response(
            TrackedTimeSerializer(timeEntries, many=True).data,
            status=200,
        )

    def stop_timer(
        self, request, workspace_slug, project_id, timer_id, *args, **kwargs
    ):
        """
        stop_timer (method): To stop the running timer
        """
        try:
            tracked_time = TrackedTime.objects.get(
                workspace__slug=workspace_slug,
                id=timer_id,
                created_by=request.user,
                project_id=project_id,
                end_time__isnull=True,
            )
        except TrackedTime.DoesNotExist:
            raise PermissionDenied("Timer not found")
        tracked_time.end_time = timezone.now()
        tracked_time.save()
        return Response(
            TrackedTimeSerializer(tracked_time).data,
            status=200,
        )

    def is_timer_running(self, request, workspace_slug, *args, **kwargs):
        """
        is_timer_running (method): To check if the timer is running for the user
        """
        timerRunning = TrackedTime.objects.get(
            workspace__slug=workspace_slug,
            created_by=request.user,
            end_time__isnull=True,
        )
        return Response(
            TrackedTimeSerializer(timerRunning).data,
            status=200,
        )


class TrackedTimeAttachmentViewSet(BaseViewSet):
    """
    TrackedTimeAttachmentViewSet (viewset): To handle all the tracked time attachment related operations
    """

    serializer_class = TrackedTimeAttachmentSerializer
    permission_classes = [
        ProjectMemberPermission,
    ]
    model = TrackedTimeAttachment
    parser_classes = (MultiPartParser, FormParser)

    def get(self, request, tracked_time_id):
        snapshots = TrackedTimeAttachment.objects.filter(
            tracked_time_id=tracked_time_id, created_by=request.user
        )
        serializer = TrackedTimeAttachmentSerializer(snapshots, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, tracked_time_id):
        tracked_time = TrackedTime.objects.get(
            id=tracked_time_id, created_by=request.user
        )
        serializer = TrackedTimeAttachmentSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(
                tracked_time=tracked_time,
                project=tracked_time.project,
                workspace=tracked_time.workspace,
                created_by=self.request.user,
                updated_by=self.request.user,
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, tracked_time_id, pk):
        snapshot = TrackedTimeAttachment.objects.get(
            pk=pk, created_by=request.user, tracked_time_id=tracked_time_id
        )
        snapshot.file.delete(save=False)
        snapshot.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
