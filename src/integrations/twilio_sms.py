from twilio.rest import Client
import structlog

from config import settings

logger = structlog.get_logger()


class TwilioSMSService:
    """Service for sending SMS messages via Twilio."""

    def __init__(self) -> None:
        if settings.twilio_account_sid and settings.twilio_auth_token:
            self.client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
            self.from_number = settings.twilio_from_number
            self.is_configured = True
        else:
            self.client = None
            self.from_number = None
            self.is_configured = False
            logger.warning("Twilio not configured - SMS disabled")

    def send_sms(self, to_number: str, message: str) -> bool:
        """Send an SMS message."""
        if not self.is_configured:
            logger.warning("Attempted to send SMS but Twilio not configured")
            return False

        try:
            # Twilio SMS limit is 1600 characters
            if len(message) > 1600:
                message = message[:1597] + "..."

            sent_message = self.client.messages.create(
                body=message,
                from_=self.from_number,
                to=to_number,
            )

            logger.info(
                "SMS sent",
                to=to_number,
                message_sid=sent_message.sid,
                status=sent_message.status,
            )
            return True

        except Exception as e:
            logger.error("Failed to send SMS", to=to_number, error=str(e))
            return False

    def send_to_user(self, message: str) -> bool:
        """Send SMS to the configured user phone number."""
        if not settings.user_phone_number:
            logger.warning("No user phone number configured")
            return False

        return self.send_sms(settings.user_phone_number, message)


# Singleton instance
sms_service = TwilioSMSService()
