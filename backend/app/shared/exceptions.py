"""NexHire exception hierarchy — shared kernel.

Direct implementation of Blueprint §17.5. Every business rule violation
maps to a stable error `code` that the frontend translates to a UI
message. The error envelope (§17.2) is built by `middleware/error_handler.py`.

Categories:
  * ValidationError     — bad input (HTTP 400)
  * AuthError           — identity/permission (HTTP 401/403)
  * BusinessRuleError   — workflow/domain rule (HTTP 422)
  * IntegrationError    — external service failure (HTTP 502/503)
  * SystemError         — unexpected/critical (HTTP 500)
"""
from __future__ import annotations

from typing import Any, ClassVar


class NexHireBaseException(Exception):
    """Base for every NexHire exception.

    Subclasses set class-level `code` and `user_message`; instances may
    override `user_message` (for cases where the message embeds runtime
    data) and add `details`.
    """

    code: ClassVar[str] = "UNEXPECTED_ERROR"
    user_message: str = "Something went wrong. Please try again."

    def __init__(
        self,
        user_message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if user_message is not None:
            self.user_message = user_message
        self.details: dict[str, Any] = details or {}
        super().__init__(self.user_message)


# ── Validation ──────────────────────────────────────────────────────
class ValidationError(NexHireBaseException):
    """Input data violates format or type constraints."""


class InvalidYearOfStudyError(ValidationError):
    code = "INVALID_YEAR_OF_STUDY"
    user_message = "Only 2nd, 3rd, and 4th year students are eligible for this program."


class GraduatedStudentIneligibleError(ValidationError):
    code = "GRADUATED_STUDENT_INELIGIBLE"
    user_message = "Graduated students are not eligible. This program is for current students only."


class MissingMandatoryFieldError(ValidationError):
    code = "MISSING_MANDATORY_FIELD"
    user_message = "Please complete all required fields before submitting."


class InvalidDateRangeError(ValidationError):
    code = "INVALID_DATE_RANGE"
    user_message = "Internship end date must be after the start date."


class InvalidStartDatePastError(ValidationError):
    code = "INVALID_START_DATE_PAST"
    user_message = "Internship start date cannot be in the past."


class InvalidFileTypeError(ValidationError):
    code = "INVALID_FILE_TYPE"
    user_message = "Only PDF, DOCX, JPG, and PNG files are accepted."


class FileTooLargeError(ValidationError):
    code = "FILE_TOO_LARGE"
    user_message = "File size exceeds the 5MB limit. Please compress and retry."


class InvalidPhoneFormatError(ValidationError):
    code = "INVALID_PHONE_FORMAT"
    user_message = "Please enter a valid phone number including country code."


class InvalidEmailFormatError(ValidationError):
    code = "INVALID_EMAIL_FORMAT"
    user_message = "Please enter a valid email address."


class InvalidPanFormatError(ValidationError):
    code = "INVALID_PAN_FORMAT"
    user_message = "PAN card number format is invalid. Expected format: ABCDE1234F"


class InvalidGovtIdFormatError(ValidationError):
    code = "INVALID_GOVT_ID_FORMAT"
    user_message = "The government ID format is invalid. Please check and re-enter."


class UnpaidConsentRequiredError(ValidationError):
    code = "UNPAID_CONSENT_REQUIRED"
    user_message = "Candidate must confirm acceptance of unpaid internship terms."


class InpersonReadyRequiredError(ValidationError):
    code = "INPERSON_READY_REQUIRED"
    user_message = "Candidate must confirm in-person availability."


class JoiningFormVersionConflictError(ValidationError):
    code = "JOINING_FORM_VERSION_CONFLICT"
    user_message = "This form was updated elsewhere. Please refresh and re-enter your changes."


class OverrideReasonTooShortError(ValidationError):
    code = "OVERRIDE_REASON_TOO_SHORT"
    user_message = (
        "Override reason must be at least 50 characters. "
        "Please provide a detailed justification."
    )


class InvalidMentorThresholdError(ValidationError):
    code = "INVALID_MENTOR_THRESHOLD"
    user_message = "Mentor threshold must be between 1 and 10."


class InvalidCoolingDurationError(ValidationError):
    code = "INVALID_COOLING_DURATION"
    user_message = "Cooling period must be between 0 and 24 months."


class InvalidTerminalStateError(ValidationError):
    code = "INVALID_TERMINAL_STATE"
    user_message = "Unknown terminal state."


class InvalidExtensionDurationError(ValidationError):
    code = "INVALID_EXTENSION_DURATION"
    user_message = "Extension cannot exceed 4 weeks per request."


# ── Auth ─────────────────────────────────────────────────────────────
class AuthError(NexHireBaseException):
    """Identity or permission failure."""


class JwtExpiredError(AuthError):
    code = "JWT_EXPIRED"
    user_message = "Your session has expired. Please log in again."


class JwtInvalidError(AuthError):
    code = "JWT_INVALID"
    user_message = "Authentication failed. Please log in again."


class SsoTokenInvalidError(AuthError):
    code = "SSO_TOKEN_INVALID"
    user_message = "Login failed. Please try again or contact IT."


class MagicLinkExpiredError(AuthError):
    code = "MAGIC_LINK_EXPIRED"
    user_message = "This link has expired. Please request a new access link from HR."


class MagicLinkUsedError(AuthError):
    code = "MAGIC_LINK_USED"
    user_message = "This link has already been used. Please request a new link."


class MagicLinkInvalidError(AuthError):
    code = "MAGIC_LINK_INVALID"
    user_message = "This link is invalid or has been tampered with."


class InsufficientPermissionsError(AuthError):
    code = "INSUFFICIENT_PERMISSIONS"
    user_message = "You don't have permission to perform this action."


class ActionTokenExpiredError(AuthError):
    code = "ACTION_TOKEN_EXPIRED"
    user_message = "This response link has expired. A new one has been sent to your email."


class ActionTokenUsedError(AuthError):
    code = "ACTION_TOKEN_USED"
    user_message = "You have already submitted your response for this request."


class CandidateRecordMismatchError(AuthError):
    code = "CANDIDATE_RECORD_MISMATCH"
    user_message = "Access denied. This record does not belong to your account."


# ── Business Rules ───────────────────────────────────────────────────
class BusinessRuleError(NexHireBaseException):
    """Valid input violates a workflow or domain rule.

    Subclasses set `rule_id` (e.g. RULE-E2) for traceability into the
    Blueprint. Every BusinessRuleError is also written to `audit_events`
    by the global error handler.
    """

    rule_id: ClassVar[str] = ""
    entity_id: str | None = None


class CollegeCapExceededError(BusinessRuleError):
    code = "COLLEGE_CAP_EXCEEDED"
    rule_id = "RULE-E2"

    def __init__(self, college: str) -> None:
        super().__init__(
            user_message=(
                f"You've reached the maximum of 2 referrals from {college}. "
                f"Select a different college."
            ),
            details={"college": college, "max_allowed": 2},
        )


class ReferrerIsMentorError(BusinessRuleError):
    code = "REFERRER_IS_MENTOR"
    rule_id = "RULE-E3"
    user_message = "The referrer and mentor cannot be the same person."


class MentorAtCapacityError(BusinessRuleError):
    code = "MENTOR_AT_CAPACITY"
    rule_id = "RULE-M-CAP"

    def __init__(self, mentor_name: str) -> None:
        super().__init__(
            user_message=(
                f"{mentor_name} currently has the maximum number of active mentees "
                f"and cannot accept new assignments."
            ),
            details={"mentor_name": mentor_name},
        )


class DuplicateCandidateBlockedError(BusinessRuleError):
    code = "DUPLICATE_CANDIDATE_BLOCKED"
    rule_id = "F-33"
    user_message = (
        "An active referral already exists for this candidate. "
        "Please check existing records."
    )


class CoolingPeriodActiveError(BusinessRuleError):
    code = "COOLING_PERIOD_ACTIVE"
    rule_id = "RULE-CP1..CP6"

    def __init__(self, terminal_state: str, ends_on: str, days_remaining: int) -> None:
        super().__init__(
            user_message=(
                f"This candidate is in a cooling period (triggered by {terminal_state}). "
                f"A new referral can be submitted after {ends_on}."
            ),
            details={
                "terminal_state": terminal_state,
                "ends_on": ends_on,
                "days_remaining": days_remaining,
            },
        )


class NdaNotSignedBlockError(BusinessRuleError):
    code = "NDA_NOT_SIGNED_BLOCK"
    rule_id = "RULE-N1"
    user_message = "Internship cannot begin. The NDA has not been signed yet."


class JoiningFormNotLockedError(BusinessRuleError):
    code = "JOINING_FORM_NOT_LOCKED"
    rule_id = "F-15"
    user_message = "The joining form must be reviewed and locked before this action."


class JoiningFormAlreadyLockedError(BusinessRuleError):
    code = "JOINING_FORM_ALREADY_LOCKED"
    rule_id = "F-15"
    user_message = "This form has been locked and can no longer be modified."


class MaxMentorAttemptsReachedError(BusinessRuleError):
    code = "MAX_MENTOR_ATTEMPTS_REACHED"
    rule_id = "RULE-M3"
    user_message = (
        "Maximum mentor assignment attempts (3) reached. This referral cannot proceed."
    )


class InvalidStateTransitionError(BusinessRuleError):
    code = "REFERRAL_NOT_IN_VALID_STATE"
    rule_id = "FSM-GUARD"

    def __init__(self, current_status: str, attempted_action: str) -> None:
        super().__init__(
            user_message=(
                f"This action cannot be performed. "
                f"The referral is currently in {current_status} state."
            ),
            details={
                "current_status": current_status,
                "attempted_action": attempted_action,
            },
        )


class MentorRejectionReasonMissingError(BusinessRuleError):
    code = "MENTOR_REJECTION_REASON_MISSING"
    rule_id = "RULE-M4"
    user_message = "A reason is required when declining a mentoring assignment."


class ExtensionAfterEndDateError(BusinessRuleError):
    code = "EXTENSION_AFTER_END_DATE"
    rule_id = "F-21"
    user_message = "Extensions must be requested before the internship end date."


class NonWorkerIdAlreadyIssuedError(BusinessRuleError):
    code = "NON_WORKER_ID_ALREADY_ISSUED"
    rule_id = "F-15"
    user_message = "A Non-Worker ID has already been issued for this intern."


class InternshipNotActiveError(BusinessRuleError):
    code = "INTERNSHIP_NOT_ACTIVE"
    rule_id = "F-22"
    user_message = "Only active internships can be closed."


class CannotPenalizeCandidateRejectedError(BusinessRuleError):
    code = "CANNOT_PENALIZE_CANDIDATE_REJECTED"
    rule_id = "RULE-CP5"
    user_message = (
        "Cooling period for 'Mentor Unavailability' must remain 0. "
        "Candidates are not at fault when mentors are unavailable."
    )


class ConfigValueUnchangedError(BusinessRuleError):
    code = "CONFIG_VALUE_UNCHANGED"
    rule_id = "S25"
    user_message = "This configuration value is already set to the requested value."


class ExtensionLimitReachedError(BusinessRuleError):
    code = "EXTENSION_LIMIT_REACHED"
    rule_id = "A16"
    user_message = "Maximum of 2 extensions per intern has been reached."


# ── Integration ──────────────────────────────────────────────────────
class IntegrationError(NexHireBaseException):
    """External service failure."""

    service: ClassVar[str] = ""
    upstream_status: int | None = None
    retryable: bool = True


class AzureOpenAiError(IntegrationError):
    code = "AZURE_OPENAI_UNAVAILABLE"
    service = "azure_openai"
    user_message = "AI features are temporarily unavailable. You can continue manually."


class AzureOpenAiRateLimitedError(IntegrationError):
    code = "AZURE_OPENAI_RATE_LIMITED"
    service = "azure_openai"
    user_message = "AI is busy. Please retry in a moment."


class AzureOpenAiQuotaExceededError(IntegrationError):
    code = "AZURE_OPENAI_QUOTA_EXCEEDED"
    service = "azure_openai"
    retryable = False
    user_message = (
        "AI features are temporarily disabled. "
        "All flows continue manually until restored."
    )


class OpenSignError(IntegrationError):
    code = "OPENSIGN_UNAVAILABLE"
    service = "opensign"
    user_message = (
        "Document signing is temporarily unavailable. "
        "It will be sent automatically when restored."
    )


class OpenSignWebhookInvalidError(IntegrationError):
    code = "OPENSIGN_WEBHOOK_INVALID"
    service = "opensign"
    retryable = False
    user_message = "Webhook signature validation failed."


class GmailApiError(IntegrationError):
    code = "GMAIL_API_UNAVAILABLE"
    service = "gmail"
    user_message = (
        "Email delivery is delayed. "
        "Your action was saved and notifications will be sent shortly."
    )


class GraphApiError(IntegrationError):
    code = "GRAPH_API_UNAVAILABLE"
    service = "microsoft_graph"
    user_message = "Account provisioning is temporarily unavailable. IT has been notified."


class AzureBlobError(IntegrationError):
    code = "AZURE_BLOB_UNAVAILABLE"
    service = "azure_blob"
    user_message = "File storage is temporarily unavailable. Please retry the upload."


class RedisUnavailableError(IntegrationError):
    code = "REDIS_UNAVAILABLE"
    service = "azure_redis"
    user_message = "A cache service is temporarily unavailable. Please retry."


class DatabaseUnavailableError(IntegrationError):
    code = "DATABASE_UNAVAILABLE"
    service = "postgres"
    user_message = "A database error occurred. Please try again."


# ── System ───────────────────────────────────────────────────────────
class SystemError(NexHireBaseException):
    """Unexpected internal error or critical infra failure."""

    code = "UNEXPECTED_ERROR"
    user_message = (
        "Something went wrong on our end. "
        "Our team has been notified. Please try again in a moment."
    )


class StateMachineViolationError(SystemError):
    code = "STATE_MACHINE_VIOLATION"
    user_message = "An invalid workflow transition was attempted."


class AuditLogFailureError(SystemError):
    code = "AUDIT_LOG_FAILURE"
    user_message = (
        "A critical system error occurred. "
        "Your action could not be completed. "
        "Please contact the system administrator immediately."
    )


class SchedulerJobFailureError(SystemError):
    code = "SCHEDULER_JOB_FAILED"


class EventBusFailureError(SystemError):
    code = "EVENT_BUS_FAILURE"
