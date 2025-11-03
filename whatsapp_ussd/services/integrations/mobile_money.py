# integrations/mobile_money.py
import requests
import logging
from typing import Dict, Any
from django.conf import settings
import base64
import uuid

logger = logging.getLogger(__name__)


class MobileMoneyAPI:
    """
    Mobile Money API integration (MTN & Airtel).
    
    Handles payment requests and status checks.
    """
    
    def __init__(self):
        self.mtn_api_url = settings.MTN_MOMO_API_URL
        self.mtn_api_key = settings.MTN_MOMO_API_KEY
        self.mtn_subscription_key = settings.MTN_MOMO_SUBSCRIPTION_KEY
        
        self.airtel_api_url = settings.AIRTEL_MONEY_API_URL
        self.airtel_api_key = settings.AIRTEL_MONEY_API_KEY
    
    def request_payment(self, phone: str, amount: int) -> Dict[str, Any]:
        """
        Initiate payment request.
        
        Args:
            phone: Customer phone number (e.g., "250788123456")
            amount: Amount in RWF
        
        Returns:
            {
                "success": True/False,
                "transaction_id": "xxx",
                "error": "error message if failed"
            }
        """
        # Determine provider based on phone prefix
        if phone.startswith('+25078') or phone.startswith('078') or phone.startswith('079'):
            return self._request_mtn_payment(phone, amount)
        elif phone.startswith('+25073') or phone.startswith('073') or phone.startswith('072'):
            return self._request_airtel_payment(phone, amount)
        else:
            return {
                "success": False,
                "error": "Unsupported mobile money provider"
            }
    
    def _request_mtn_payment(self, phone: str, amount: int) -> Dict[str, Any]:
        """Request MTN Mobile Money payment"""
        try:
            # Generate reference ID
            reference_id = str(uuid.uuid4())
            
            # Prepare request
            url = f"{self.mtn_api_url}/collection/v1_0/requesttopay"
            
            headers = {
                "Authorization": f"Bearer {self._get_mtn_access_token()}",
                "X-Reference-Id": reference_id,
                "X-Target-Environment": settings.MTN_MOMO_ENVIRONMENT,
                "Ocp-Apim-Subscription-Key": self.mtn_subscription_key,
                "Content-Type": "application/json"
            }
            
            payload = {
                "amount": str(amount),
                "currency": "RWF",
                "externalId": reference_id,
                "payer": {
                    "partyIdType": "MSISDN",
                    "partyId": phone.replace('+', '').replace(' ', '')
                },
                "payerMessage": "Payment for Twara subscription",
                "payeeNote": f"Twara subscription {amount}RWF"
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            
            if response.status_code in [200, 202]:
                logger.info(f"MTN payment requested: {reference_id}")
                return {
                    "success": True,
                    "transaction_id": reference_id
                }
            else:
                logger.error(f"MTN payment request failed: {response.status_code} {response.text}")
                return {
                    "success": False,
                    "error": f"MTN API error: {response.status_code}"
                }
        
        except Exception as e:
            logger.exception(f"MTN payment request error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _request_airtel_payment(self, phone: str, amount: int) -> Dict[str, Any]:
        """Request Airtel Money payment"""
        try:
            # Generate reference ID
            reference_id = str(uuid.uuid4())
            
            url = f"{self.airtel_api_url}/merchant/v1/payments/"
            
            headers = {
                "Authorization": f"Bearer {self._get_airtel_access_token()}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "reference": reference_id,
                "subscriber": {
                    "country": "RW",
                    "currency": "RWF",
                    "msisdn": phone.replace('+', '').replace(' ', '')
                },
                "transaction": {
                    "amount": amount,
                    "country": "RW",
                    "currency": "RWF",
                    "id": reference_id
                }
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            
            if response.status_code in [200, 201]:
                data = response.json()
                logger.info(f"Airtel payment requested: {reference_id}")
                return {
                    "success": True,
                    "transaction_id": data.get('data', {}).get('transaction', {}).get('id', reference_id)
                }
            else:
                logger.error(f"Airtel payment request failed: {response.status_code} {response.text}")
                return {
                    "success": False,
                    "error": f"Airtel API error: {response.status_code}"
                }
        
        except Exception as e:
            logger.exception(f"Airtel payment request error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def check_payment_status(self, transaction_id: str) -> str:
        """
        Check payment status.
        
        Returns:
            "SUCCESSFUL" | "FAILED" | "PENDING"
        """
        # Try MTN first
        status = self._check_mtn_payment_status(transaction_id)
        if status != "UNKNOWN":
            return status
        
        # Try Airtel
        return self._check_airtel_payment_status(transaction_id)
    
    def _check_mtn_payment_status(self, transaction_id: str) -> str:
        """Check MTN payment status"""
        try:
            url = f"{self.mtn_api_url}/collection/v1_0/requesttopay/{transaction_id}"
            
            headers = {
                "Authorization": f"Bearer {self._get_mtn_access_token()}",
                "X-Target-Environment": settings.MTN_MOMO_ENVIRONMENT,
                "Ocp-Apim-Subscription-Key": self.mtn_subscription_key
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                status = data.get('status', 'PENDING')
                
                if status == 'SUCCESSFUL':
                    return "SUCCESSFUL"
                elif status == 'FAILED':
                    return "FAILED"
                else:
                    return "PENDING"
            
            return "UNKNOWN"
        
        except Exception as e:
            logger.error(f"MTN status check error: {e}")
            return "UNKNOWN"
    
    def _check_airtel_payment_status(self, transaction_id: str) -> str:
        """Check Airtel payment status"""
        try:
            url = f"{self.airtel_api_url}/standard/v1/payments/{transaction_id}"
            
            headers = {
                "Authorization": f"Bearer {self._get_airtel_access_token()}"
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                status = data.get('data', {}).get('transaction', {}).get('status', 'PENDING')
                
                if status in ['TS', 'SUCCESSFUL']:
                    return "SUCCESSFUL"
                elif status in ['TF', 'FAILED']:
                    return "FAILED"
                else:
                    return "PENDING"
            
            return "UNKNOWN"
        
        except Exception as e:
            logger.error(f"Airtel status check error: {e}")
            return "UNKNOWN"
    
    def _get_mtn_access_token(self) -> str:
        """Get MTN API access token"""
        try:
            url = f"{self.mtn_api_url}/collection/token/"
            
            # Create basic auth header
            api_user = settings.MTN_MOMO_API_USER
            api_key = settings.MTN_MOMO_API_KEY
            credentials = base64.b64encode(f"{api_user}:{api_key}".encode()).decode()
            
            headers = {
                "Authorization": f"Basic {credentials}",
                "Ocp-Apim-Subscription-Key": self.mtn_subscription_key
            }
            
            response = requests.post(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('access_token', '')
            
            logger.error(f"Failed to get MTN token: {response.status_code}")
            return ""
        
        except Exception as e:
            logger.exception(f"MTN token error: {e}")
            return ""
    
    def _get_airtel_access_token(self) -> str:
        """Get Airtel API access token"""
        try:
            url = f"{self.airtel_api_url}/auth/oauth2/token"
            
            headers = {
                "Content-Type": "application/json"
            }
            
            payload = {
                "client_id": settings.AIRTEL_MONEY_CLIENT_ID,
                "client_secret": settings.AIRTEL_MONEY_CLIENT_SECRET,
                "grant_type": "client_credentials"
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('access_token', '')
            
            logger.error(f"Failed to get Airtel token: {response.status_code}")
            return ""
        
        except Exception as e:
            logger.exception(f"Airtel token error: {e}")
            return ""