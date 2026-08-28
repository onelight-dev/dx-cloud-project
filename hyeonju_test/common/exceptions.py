class ApiError(Exception):
    status_code = 400

    def __init__(self, message: str, status_code: int = None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class BadRequestError(ApiError):
    status_code = 400


class UnauthorizedError(ApiError):
    status_code = 401


class NotFoundError(ApiError):
    status_code = 404