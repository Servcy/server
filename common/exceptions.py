from django.db import DatabaseError
from newrelic.agent import notice_error
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler


class ServcyBaseException(Exception):
    """
    Custom exception base for Servcy.
    """

    @property
    def message(self):
        return str(self)


class ServcyOauthCodeException(ServcyBaseException):
    """
    Exception raised when oauth code is not provided.
    """


class ServcyAPIException(APIException, ServcyBaseException):
    """
    APIException for Servcy server.
    """

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Servcy API encountered an error!"
    default_code = "APIException"


class MicroserviceException(ServcyAPIException):
    """
    For Servcy Microservices.
    """

    default_detail = "A Servcy microservice encountered an error!"
    default_code = "MicroServiceException"


class BusinessException(ServcyAPIException):
    """
    For Servcy Business Logic.
    """

    default_detail = "A Business Exception has occurred"
    default_code = "BusinessException"


class ServcyDBException(DatabaseError, ServcyBaseException):
    """
    For Database Exception BaseClass.
    """


class DisplayableException(ServcyBaseException):
    """
    For exceptions that have error messages that can be directly exposed to the user.
    """


class DataException(Exception):
    """
    For custom classification of errors.
    """

    @property
    def message(self):
        return str(self)


class SerializerException(ServcyBaseException):
    """
    For exception raised from serializers.
    """

    default_detail = "A Serializer Exception has occured"
    default_code = "SerializerException"


class WriteSerializerException(SerializerException):
    """
    For exception raises from Write Serializers.
    """

    default_detail = "Exception occured while writing serializer"
    default_code = "WriteSerializer exception"


class ReadSerializerException(SerializerException):
    """
    For exceptions raised from Read Serializers.
    """

    default_detail = "Exception occured while reading serializer"
    default_code = "ReadSerializer exception"


class InadequateDataException(BusinessException):
    """
    For exceptions raised when data is inadequate.
    """

    status_code = status.HTTP_412_PRECONDITION_FAILED
    default_detail = "Inadequate data available"


class JsonDataException(BusinessException):
    """
    For exceptions raised when JSON data is invalid.
    """

    status_code = status.HTTP_412_PRECONDITION_FAILED
    default_detail = "JSON data is invalid. Possible Key Exception."


class ServcyExceptionHandler:
    """
    Exception handler for Servcy.
    """

    @staticmethod
    def main(exception, context):
        """
        Main exception handler for Servcy.
        """
        notice_error(exception)
        response = exception_handler(exception, context)
        if response is not None:
            response.data["status_code"] = response.status_code
        return response
