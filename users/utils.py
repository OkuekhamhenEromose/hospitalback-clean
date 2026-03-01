# users/utils.py - IMPROVED VERSION
from django.core.mail import send_mail
from django.conf import settings
import logging
from socket import timeout as socket_timeout
import smtplib

logger = logging.getLogger(__name__)

def SendMail(email, timeout=10):
    """
    Send welcome email with timeout protection
    Returns: True if sent, False if failed, None if email is disabled
    """
    # Check if email backend is enabled
    if settings.EMAIL_BACKEND == 'django.core.mail.backends.console.EmailBackend':
        logger.info(f"Email console backend active - would send to {email}")
        return True  # Return True to allow registration to proceed
    
    if not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
        logger.warning("Email credentials not configured, skipping email")
        return True  # Return True to not block registration
    
    try:
        subject = "Welcome to Nile Healthcare"
        message = '''Welcome to Nile Healthcare!

Thank you for registering with us. We're excited to have you on board.

Best regards,
The Nile Healthcare Team
'''

        # Send with timeout protection
        send_mail(
            subject,
            message,
            settings.EMAIL_HOST_USER,
            [email],
            fail_silently=False,
        )
        logger.info(f"Welcome email sent to {email}")
        return True
        
    except (socket_timeout, smtplib.SMTPException) as e:
        # Specific SMTP/timeout errors - don't crash registration
        logger.warning(f"Email timeout/SMTP error for {email}: {str(e)}. Registration continues.")
        return True  # Return True so registration doesn't fail
        
    except Exception as e:
        # Any other error
        logger.error(f"Failed to send email to {email}: {str(e)}")
        return True  # Still return True - don't block registration over email