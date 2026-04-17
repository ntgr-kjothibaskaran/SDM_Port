#!/usr/bin/env python3
import asyncio
import json
import logging
import time
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox, scrolledtext
from typing import Dict, List, Optional
import threading

try:
    import aiohttp
    import requests
    import jwt
    from datetime import datetime
except ImportError:
    print("Installing required dependencies...")
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "aiohttp", "requests", "PyJWT"])
    import aiohttp
    import requests
    import jwt
    from datetime import datetime

print("SDM Manager: Authentication ready.")

# Configuration for Multiple Environments
class Config:
    # Environment Configurations (Based on actual project environments)
    ENVIRONMENTS = {
        "pri-qa": {
            "name": "Primary QA Environment",
            "api_base_url": "https://pri-qa-api-web.insight.netgear.com/insightappcom/",
            "api_key": "pP3dO6k6lf2N83UEWUjH480VUXhtqCNqa0g8ONeM",
            "web_url": "https://pri-qa.insight.netgear.com",
        },
        "demo-aux": {
            "name": "Demo Aux Environment",
            "api_base_url": "https://demo-aux-api-web.insight.netgear.com/insightappcom/",
            "api_key": "pP3dO6k6lf2N83UEWUjH480VUXhtqCNqa0g8ONeM",
            "web_url": "https://demo-aux.insight.netgear.com"
        },
        "maint-qa": {
            "name": "Maintenance QA Environment",
            "api_base_url": "https://maint-qa-api-web.insight.netgear.com/insightappcom/",
            "api_key": "pP3dO6k6lf2N83UEWUjH480VUXhtqCNqa0g8ONeM",
            "web_url": "https://maint-qa.insight.netgear.com",
        },
        "production": {
            "name": "Production Environment",
            "api_base_url": "https://api-web.insight.netgear.com/insightappcom/",
            "api_key": "pP3dO6k6lf2N83UEWUjH480VUXhtqCNqa0g8ONeM",
            "web_url": "https://insight.netgear.com",
        },
        "beta": {
            "name": "Beta Environment",
            "api_base_url": "https://beta-api-web.insight.netgear.com/insightappcom/",
            "api_key": "pP3dO6k6lf2N83UEWUjH480VUXhtqCNqa0g8ONeM",
            "web_url": "https://beta.insight.netgear.com"
        },
        "demo": {
            "name": "Demo Environment",
            "api_base_url": "https://demo-api-web.insight.netgear.com/insightappcom/",
            "api_key": "pP3dO6k6lf2N83UEWUjH480VUXhtqCNqa0g8ONeM",
            "web_url": "https://demo.insight.netgear.com"
        },
        "maint-beta": {
            "name": "Maintenance Beta Environment", 
            "api_base_url": "https://maint-beta-api-web.insight.netgear.com/insightappcom/",
            "api_key": "pP3dO6k6lf2N83UEWUjH480VUXhtqCNqa0g8ONeM",
            "web_url": "https://maint-beta.insight.netgear.com"
        },
        "maint-dev": {
            "name": "Maintenance Dev Environment",
            "api_base_url": "https://maint-dev-api-web.insight.netgear.com/insightappcom/",
            "api_key": "pP3dO6k6lf2N83UEWUjH480VUXhtqCNqa0g8ONeM",
            "web_url": "https://maint-dev.insight.netgear.com"
        },
        "pri-dev": {
            "name": "Primary Dev Environment",
            "api_base_url": "https://pri-dev-api-web.insight.netgear.com/insightappcom/",
            "api_key": "pP3dO6k6lf2N83UEWUjH480VUXhtqCNqa0g8ONeM",
            "web_url": "https://pri-dev.insight.netgear.com"
        }
    }
    
    # Default environment
    DEFAULT_ENVIRONMENT = "pri-qa"
    
    # Common settings
    REQUEST_TIMEOUT = 30
    SDM_ENABLE_TIMEOUT = 180
    SDM_CHECK_INTERVAL = 10
    MAX_RETRIES = 3
    
    def __init__(self, environment="pri-qa"):
        self.set_environment(environment)
    
    def set_environment(self, environment):
        """Set the current environment."""
        if environment not in self.ENVIRONMENTS:
            environment = self.DEFAULT_ENVIRONMENT
            
        env_config = self.ENVIRONMENTS[environment]
        self.current_environment = environment
        self.API_BASE_URL = env_config["api_base_url"]
        self.API_KEY = env_config["api_key"]
        self.WEB_URL = env_config["web_url"]
        self.ENVIRONMENT_NAME = env_config["name"]
        
    
    def get_available_environments(self):
        """Get list of available environments."""
        return list(self.ENVIRONMENTS.keys())
    
    def get_environment_display_names(self):
        """Get display names for environments."""
        return [f"{env} ({config['name']})" for env, config in self.ENVIRONMENTS.items()]

# Data Models
class AuthResponse:
    def __init__(self, data):
        self.success = data.get("status", False) or data.get("success", False)
        
        # Handle different response formats
        if "data" in data:
            # Format 1: {status: true, data: {_id, email, accessToken}, accountId}
            user_data = data.get("data", {})
            self.user_id = user_data.get("_id", "")
            self.token = user_data.get("accessToken", "")
            self.email = user_data.get("email", "")
            self.account_id = data.get("accountId", self.user_id)
        else:
            # Format 2: Direct format or other variations
            self.user_id = data.get("_id", data.get("userId", ""))
            self.token = data.get("accessToken", data.get("token", ""))
            self.email = data.get("email", "")
            self.account_id = data.get("accountId", self.user_id)
        
        self.user_role = data.get("UserRole", [])
        
        # Store additional tokens if available (for Cognito responses)
        self.tokens = data.get("tokens", {})

class Organization:
    def __init__(self, data):
        self.orgId = data.get("orgId", "")
        self.orgName = data.get("orgName", "")
        self.locationCount = data.get("locationCount", "0")
        self.deviceCount = data.get("deviceCount", 0)

class Location:
    def __init__(self, data):
        self.networkId = data.get("networkId", "")
        self.networkName = data.get("networkName", "")
        self.name = self.networkName  # For compatibility
        self.apCount = data.get("apCount", 0)
        self.device_count = data.get("deviceCount", 0)  # For compatibility
        self.deviceCount = self.device_count

class APDevice:
    def __init__(self, data):
        # Handle both old and new data formats
        self.deviceId = data.get("deviceId", data.get("_id", ""))
        self.serialNo = data.get("serialNo", "")
        self.name = data.get("deviceName", data.get("name", ""))
        self.model = data.get("model", "")
        self.ipAddress = data.get("ipSettings", data.get("ipAddress", ""))
        self.macAddress = data.get("macAddress", "")
        self.networkId = data.get("networkId", "")
        self.networkName = data.get("networkName", "")
        self.deviceStatus = data.get("deviceStatus", 0)  # Integer: 1=online, 0=offline
        self.lastSeen = data.get("lastSeen", 0)
        self.sdmStatus = "0"
        self.sdmPort = None



# Authentication Service
class AuthService:
    def __init__(self, config=None):
        self.config = config or Config()

    def authenticate_user(self, email: str, password: str) -> Optional[AuthResponse]:
        """Authenticate user with Swagger API."""
        try:
            print(f"Starting email/password authentication for: {email}")
            
            # Use the backend Swagger authenticate endpoint
            print("Attempting Swagger authenticate endpoint...")
            auth_result = self._try_swagger_authenticate(email, password)
            if auth_result and auth_result.success:
                print("SUCCESS: Direct email/password authentication succeeded!")
                return auth_result
            else:
                print("ERROR: Direct authentication failed")
                print("TIP: Try Manual Credentials if email/password doesn't work")
            
            return None
                
        except Exception as e:
            print(f"Authentication error: {str(e)}")
            return None

    def _try_swagger_authenticate(self, email: str, password: str) -> Optional[AuthResponse]:
        """Try direct Swagger authenticate endpoint based on backend analysis."""
        try:
            print(f"Using backend Swagger authentication API for: {email}")
            
            # Simple payload - backend only needs email and password
            auth_data = {
                "email": email,
                "password": password
            }
            
            # Minimal headers - backend doesn't require complex browser headers
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            # Call the Spring Boot SwaggerAuthController endpoint
            response = requests.post(
                f"{self.config.API_BASE_URL}public/v1/swagger/authenticate",
                json=auth_data,
                headers=headers,
                timeout=self.config.REQUEST_TIMEOUT
            )
            
            print(f"Swagger authenticate status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"Swagger authenticate response: {result}")
                
                # Check if MFA is required first
                if result.get("mfaRequired"):
                    print("MFA/2FA is required for this account")
                    challenge_name = result.get("challengeName", "")
                    session = result.get("session", "")
                    print(f"Challenge: {challenge_name}")
                    
                    # For now, we'll return None for MFA cases
                    # TODO: Implement MFA flow with /public/v1/swagger/verify-mfa
                    print("ERROR: MFA handling not yet implemented in Python GUI")
                    print("TIP: Use Manual Credentials if you have browser session with MFA already completed")
                    return None
                
                # Check for successful authentication
                elif result.get("success"):
                    print("SUCCESS: Direct authentication successful!")
                    
                    # Extract data from backend response format
                    token = result.get("token", "")  # Backend access token
                    account_id = result.get("accountId", "")
                    user_id = result.get("userId", result.get("_id", ""))
                    email_resp = result.get("email", email)
                    api_key = result.get("apiKey", "")  # Backend provides this
                    
                    print(f"User ID: {user_id}")
                    print(f"Account ID: {account_id}")
                    print(f"Email: {email_resp}")
                    
                    # Create AuthResponse matching our expected format
                    auth_data = {
                        'status': True,
                        'data': {
                            '_id': user_id,
                            'email': email_resp,
                            'accessToken': token
                        },
                        'accountId': account_id,
                        'backend_api_key': api_key  # Store the API key from backend
                    }
                    
                    return AuthResponse(auth_data)
                
                else:
                    # Authentication failed
                    error_msg = result.get("error", "Authentication failed")
                    error_type = result.get("errorType", "")
                    print(f"ERROR: Authentication failed: {error_msg}")
                    if error_type:
                        print(f"Error type: {error_type}")
                    return None
                    
            elif response.status_code == 400:
                print("ERROR: Bad request - check email and password format")
                return None
            elif response.status_code == 401:
                result = response.json() if response.text else {}
                error_msg = result.get("error", "Invalid credentials")
                error_type = result.get("errorType", "")
                print(f"ERROR: Authentication failed: {error_msg}")
                if error_type:
                    print(f"   Error type: {error_type}")
                print("TIP: Double-check your email and password are correct for this environment")
                return None
            elif response.status_code == 500:
                print("ERROR: Server error - Authentication service may be unreachable")
                return None
            else:
                print(f"ERROR: Unexpected response: {response.status_code}")
                return None
                    
        except Exception as e:
            print(f"Swagger authenticate exception: {str(e)}")
            return None
    





# Async API Client
class InsightCloudAPI:
    def __init__(self, config=None):
        self.config = config or Config()
        self.session = None

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=self.config.REQUEST_TIMEOUT)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    def _get_headers(self, user_id, account_id, token, **kwargs):
        # Clean token in case it comes from cookie format
        clean_token = token
        if "accessToken=" in token:
            clean_token = token.split("accessToken=")[1].split(";")[0]
        
        headers = {
            "apikey": self.config.API_KEY,  # lowercase to match working curl
            "accountid": account_id,        # lowercase to match working curl
            "token": clean_token,
            "content-type": "application/json",
            "accept": "application/json, text/plain, */*",
            "origin": self.config.WEB_URL,
            "referer": f"{self.config.WEB_URL}/"
        }
        # Add networkid header for device APIs (lowercase to match curl)
        if "networkid" in kwargs:
            headers["networkid"] = kwargs["networkid"]
        return headers

    async def _make_request(self, method, endpoint, user_id, account_id, token, data=None, **kwargs):
        url = self.config.API_BASE_URL + endpoint
        headers = self._get_headers(user_id, account_id, token, **kwargs)
        
        print(f"Making {method} request to: {url}")
        print(f"Headers: {headers}")
        if data:
            print(f"Data: {data}")
        
        for attempt in range(self.config.MAX_RETRIES):
            try:
                async with self.session.request(
                    method=method, url=url, headers=headers, json=data
                ) as response:
                    print(f"Response status: {response.status}")
                    
                    try:
                        result = await response.json()
                        print(f"Response body: {result}")
                    except:
                        text = await response.text()
                        print(f"Response text: {text}")
                        raise Exception(f"Invalid JSON response: {text[:200]}...")
                    
                    if response.status == 200:
                        return result
                    elif response.status == 401:
                        raise Exception(f"Authentication failed (401): {result.get('message', 'Invalid credentials')}")
                    elif response.status == 403:
                        raise Exception(f"Access forbidden (403): {result.get('message', 'Insufficient permissions')}")
                    elif response.status == 404:
                        raise Exception(f"Endpoint not found (404): {url}")
                    else:
                        if attempt == self.config.MAX_RETRIES - 1:
                            raise Exception(f"API error ({response.status}): {result.get('message', 'Unknown error')}")
                        
            except Exception as e:
                print(f"Request attempt {attempt + 1} failed: {str(e)}")
                if attempt == self.config.MAX_RETRIES - 1:
                    raise e
                await asyncio.sleep(2 ** attempt)

    async def get_organizations(self, user_id, account_id, token):
        print(f"Fetching organizations for user {user_id}")
        print(f"Using corrected API base URL: {self.config.API_BASE_URL}")
        endpoint = f"organization/v1/orgInfo/{user_id}"
        
        try:
            result = await self._make_request("GET", endpoint, user_id, account_id, token)
            print(f"Organizations response: {result}")
            
            if result.get("response", {}).get("status"):
                orgs = [Organization(org) for org in result.get("details", [])]
                print(f"Successfully fetched {len(orgs)} organizations")
                return orgs
            else:
                error_msg = result.get("response", {}).get("message", "Failed to fetch organizations")
                print(f"API returned error: {error_msg}")
                raise Exception(f"API Error: {error_msg}")
                
        except Exception as e:
            print(f"Failed to fetch organizations: {str(e)}")
            raise Exception(f"Failed to fetch organizations from API: {str(e)}")


    async def get_locations(self, user_id, account_id, token, org_id):
        print(f"Fetching locations for user {user_id}, org {org_id}")
        
        # Use the EXACT format that works from the curl command
        try:
            endpoint = f"network/v1/locationGridDetails/{user_id}/{org_id}/0"
            print(f"Using CORRECT endpoint format: PUT {endpoint}")
            
            # Use empty JSON object like in the working curl command
            empty_data = {}
            result = await self._make_request("PUT", endpoint, user_id, account_id, token, data=empty_data)
            
            print(f"Response status: {result.get('response', {}).get('status')}")
            print(f"Response message: {result.get('response', {}).get('message', 'No message')}")
            
            if result.get("response", {}).get("status"):
                # Extract location info from the response (NOT details - that's pagination)
                location_info = result.get("info", [])
                
                if location_info:
                    print(f"✅ Found {len(location_info)} locations using correct endpoint")
                    
                    locations = []
                    for i, loc_data in enumerate(location_info):
                        try:
                            # Now we know loc_data is always a dict from the "info" array
                            location_obj = Location({
                                "networkId": loc_data.get("networkId", f"network_{i}"),
                                "networkName": loc_data.get("networkName", f"Location {i+1}"),
                                "deviceCount": loc_data.get("totalDevice", 0),  # Use totalDevice from API
                                "apCount": loc_data.get("totalDevice", 0)  # Use totalDevice as AP count
                            })
                                
                            locations.append(location_obj)
                            print(f"  - {location_obj.name} (ID: {location_obj.networkId}, {location_obj.device_count} devices)")
                            
                        except Exception as e:
                            print(f"  ERROR processing location {i}: {str(e)}")
                    
                    return locations
                else:
                    print("⚠️ No location details found in response")
                    return []
                    
            else:
                error_msg = result.get("response", {}).get("message", "Unknown error")
                print(f"❌ API Error: {error_msg}")
                return []
            
        except Exception as e:
            print(f"❌ Exception fetching locations: {str(e)}")
            return []


    async def get_ap_devices(self, user_id, account_id, token, network_id):
        print(f"Fetching AP devices for network {network_id}")
        
        # Use the EXACT device API format from your working curl command
        try:
            endpoint = f"device/v1/deviceList/{user_id}/{network_id}/0"
            print(f"Using CORRECT device endpoint: PUT {endpoint}")
            
            # Add networkid header as required by the device API
            result = await self._make_request("PUT", endpoint, user_id, account_id, token, data={}, networkid=network_id)
            
            print(f"Device API response status: {result.get('response', {}).get('status')}")
            print(f"Device API response message: {result.get('response', {}).get('message', 'No message')}")
            
            if result.get("response", {}).get("status"):
                # Extract devices from the response - they're in details.data
                details = result.get("details", {})
                devices_data = details.get("data", []) if isinstance(details, dict) else []
                
                if devices_data:
                    print(f"Found {len(devices_data)} devices from device API")
                    
                    # Filter for AP devices and create APDevice objects
                    ap_devices = []
                    for device_data in devices_data:
                        try:
                            # Ensure device_data is a dict
                            if not isinstance(device_data, dict):
                                continue
                                
                            device_type = device_data.get("deviceType", "").upper()
                            if device_type == "AP":
                                ap_device = APDevice(device_data)
                                ap_devices.append(ap_device)
                                print(f"  - AP Device: {ap_device.name} ({ap_device.serialNo}) - {ap_device.model}")
                                
                        except Exception as e:
                            print(f"  Error processing device: {str(e)}")
                    
                    if ap_devices:
                        print(f"SUCCESS: Found {len(ap_devices)} AP devices in network {network_id}")
                        return ap_devices
                    else:
                        print(f"WARNING: Found {len(devices_data)} devices but none are AP type")
                        # Show device types for debugging
                        device_types = list(set(d.get("deviceType", "Unknown") for d in devices_data))
                        print(f"Available device types: {device_types}")
                        return []
                else:
                    print("WARNING: No devices found in device API response")
                    return []
                    
            else:
                error_msg = result.get("response", {}).get("message", "Unknown error")
                print(f"ERROR: Device API failed - {error_msg}")
                return []
                
        except Exception as e:
            print(f"ERROR: Exception fetching devices - {str(e)}")
            return []


    async def get_sdm_status(self, user_id, account_id, token, device_id, network_id):
        print(f"Fetching SDM status for device {device_id}")
        
        # Use correct endpoints from apiConfig.js
        # GET_SDM_DETAILS: GET device/v1/sdmstatus/{_Id}/{selectedDeviceId}
        # GET_AP_DIAGNOSTIC_MODE: GET device/v1/sdmstatus/{_Id}/{deviceId}
        
        endpoints_to_try = [
            f"device/v1/sdmstatus/{user_id}/{device_id}",  # Both endpoints use same pattern
        ]
        
        for endpoint in endpoints_to_try:
            try:
                print(f"Trying SDM endpoint: GET {endpoint}")
                result = await self._make_request("GET", endpoint, user_id, account_id, token, networkid=network_id)
                
                print(f"  Response status: {result.get('response', {}).get('status')}")
                print(f"  Full response: {result}")
                
                if result.get("response", {}).get("status"):
                    details = result.get("details", {})
                    status = details.get("status", "0")
                    port = details.get("port")
                    print(f"✅ Got SDM status: {status}, port: {port}")
                    return status, port
                else:
                    error_msg = result.get("response", {}).get("message", "Unknown error")
                    print(f"  Error: {error_msg}")
                    
            except Exception as e:
                print(f"GET {endpoint} failed: {str(e)}")
        
        print("❌ SDM endpoint failed, returning default values")
        return "0", None


    async def set_sdm_status(self, user_id, account_id, token, device_id, network_id, enable):
        print(f"{'Enabling' if enable else 'Disabling'} SDM for device {device_id}")
        
        # Use correct endpoint from apiConfig.js
        # SAVE_SDM_DETAILS: POST device/v1/sdmstatus/{_Id}/{selectedDeviceId}
        endpoint = f"device/v1/sdmstatus/{user_id}/{device_id}"
        sdm_data = {"status": "1" if enable else "0"}
        
        try:
            print(f"Trying SDM set endpoint: POST {endpoint}")
            result = await self._make_request("POST", endpoint, user_id, account_id, token, data=sdm_data, networkid=network_id)
            
            print(f"  Response status: {result.get('response', {}).get('status')}")
            print(f"  Full response: {result}")
            
            if result.get("response", {}).get("status"):
                print(f"✅ Successfully {'enabled' if enable else 'disabled'} SDM")
                return True
            else:
                error_msg = result.get("response", {}).get("message", "Unknown error")
                print(f"  Error: {error_msg}")
                raise Exception(f"API Error: {error_msg}")
                
        except Exception as e:
            print(f"POST {endpoint} failed: {str(e)}")
            raise Exception(f"Failed to {'enable' if enable else 'disable'} SDM for device {device_id}: {str(e)}")

    async def share_diagnostics(self, user_id, account_id, token, device_id, network_id, email_list):
        """Share device diagnostics with specified email addresses."""
        print(f"Sharing diagnostics for device {device_id} with emails: {email_list}")
        
        # Use the v2 diagnostic endpoint from DeviceController
        endpoint = f"device/v2/diagnostic/{device_id}/{user_id}"
        
        # Build the diagnostic info payload structure based on the backend code
        diagnostic_data = {
            "diagnosticInfo": [
                {"email": email.strip()} for email in email_list
            ]
        }
        
        try:
            print(f"Sharing diagnostics endpoint: POST {endpoint}")
            print(f"Diagnostic data: {diagnostic_data}")
            
            result = await self._make_request("POST", endpoint, user_id, account_id, token, 
                                            data=diagnostic_data, networkid=network_id)
            
            print(f"Diagnostics share response status: {result.get('response', {}).get('status')}")
            print(f"Full diagnostics response: {result}")
            
            if result.get("response", {}).get("status"):
                print("✅ Successfully shared diagnostics")
                return True
            else:
                error_msg = result.get("response", {}).get("message", "Unknown error")
                print(f"Error: {error_msg}")
                raise Exception(f"API Error: {error_msg}")
                
        except Exception as e:
            print(f"POST {endpoint} failed: {str(e)}")
            raise Exception(f"Failed to share diagnostics for device {device_id}: {str(e)}")

# GUI Application
class SDMManagerGUI:
    def __init__(self):
        self.config = Config()
        self.auth_service = AuthService(self.config)
        self.auth_response = None
        self.organizations = []
        self.locations = []
        self.ap_devices = []
        
        # Setup logging
        logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
        
        # Create main window
        self.root = tk.Tk()
        self.root.title(f"AP SDM Port Manager - {self.config.ENVIRONMENT_NAME}")
        self.root.geometry("1400x900")
        self.root.minsize(1200, 700)
        
        # Configure modern styling
        self.setup_styles()
        
        # Setup UI
        self.setup_ui()
        
    def setup_styles(self):
        """Configure modern styling and themes."""
        try:
            from tkinter import ttk
            
            # Configure ttk styles
            style = ttk.Style()
            
            # Use a modern theme if available
            available_themes = style.theme_names()
            if 'vista' in available_themes:
                style.theme_use('vista')
            elif 'clam' in available_themes:
                style.theme_use('clam')
            
            # Configure custom styles
            style.configure('Title.TLabel', font=('Segoe UI', 18, 'bold'), foreground='#2c3e50')
            style.configure('Subtitle.TLabel', font=('Segoe UI', 11), foreground='#7f8c8d')
            style.configure('Header.TLabel', font=('Segoe UI', 12, 'bold'), foreground='#34495e')
            style.configure('Success.TLabel', font=('Segoe UI', 10), foreground='#27ae60')
            style.configure('Error.TLabel', font=('Segoe UI', 10), foreground='#e74c3c')
            style.configure('Warning.TLabel', font=('Segoe UI', 10), foreground='#f39c12')
            
            # Button styles
            style.configure('Primary.TButton', font=('Segoe UI', 10, 'bold'))
            style.configure('Success.TButton', font=('Segoe UI', 10))
            style.configure('Danger.TButton', font=('Segoe UI', 10))
            
            # Notebook styling
            style.configure('TNotebook.Tab', padding=[20, 10])
            
        except Exception as e:
            print(f"Note: Could not configure advanced styling: {e}")
        
        # Set window background
        self.root.configure(bg='#f8f9fa')

    def setup_ui(self):
        """Setup the GUI components."""
        # Main container with better spacing
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)
        
        # Header section
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 20))
        
        # Title with modern styling
        title_label = ttk.Label(header_frame, text="🔧 AP SDM Port Manager", style='Title.TLabel')
        title_label.pack()
        
        subtitle_label = ttk.Label(header_frame, text=f"Netgear Insight Cloud - {self.config.ENVIRONMENT_NAME}", style='Subtitle.TLabel')
        subtitle_label.pack(pady=(5, 0))
        
        # Status bar
        self.status_frame = ttk.Frame(header_frame)
        self.status_frame.pack(fill=tk.X, pady=(15, 0))
        
        self.connection_status = ttk.Label(self.status_frame, text="⚫ Disconnected", style='Error.TLabel')
        self.connection_status.pack(side=tk.LEFT)
        
        self.user_status = ttk.Label(self.status_frame, text="", style='Subtitle.TLabel')
        self.user_status.pack(side=tk.RIGHT)
        
        # Create notebook for tabs
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Authentication tab
        self.setup_auth_tab()
        
        # Management tab
        self.setup_management_tab()
        
        # Log tab
        self.setup_log_tab()
        
    def setup_auth_tab(self):
        """Setup authentication tab with modern design."""
        auth_frame = ttk.Frame(self.notebook)
        self.notebook.add(auth_frame, text="Authentication")
        
        # Create a centered container
        container = ttk.Frame(auth_frame)
        container.pack(expand=True, fill=tk.BOTH, padx=40, pady=40)
        
        # Welcome section
        welcome_frame = ttk.Frame(container)
        welcome_frame.pack(fill=tk.X, pady=(0, 30))
        
        welcome_label = ttk.Label(welcome_frame, text="Welcome to SDM Manager", style='Header.TLabel')
        welcome_label.pack()
        
        instruction_label = ttk.Label(welcome_frame, text="Please authenticate to manage your AP devices", style='Subtitle.TLabel')
        instruction_label.pack(pady=(5, 0))
        
        # Login form with better styling
        login_frame = ttk.LabelFrame(container, text=" Login Credentials ", padding=30)
        login_frame.pack(fill=tk.X, pady=(0, 20))
        
        # Environment selector
        ttk.Label(login_frame, text="Environment:", font=('Segoe UI', 10)).grid(row=0, column=0, sticky="w", pady=(0, 15))
        self.environment_var = tk.StringVar(value=self.config.DEFAULT_ENVIRONMENT)
        self.environment_combo = ttk.Combobox(
            login_frame, 
            textvariable=self.environment_var, 
            values=self.config.get_available_environments(),
            state="readonly", 
            width=47, 
            font=('Segoe UI', 10)
        )
        self.environment_combo.grid(row=0, column=1, sticky="ew", pady=(0, 15), padx=(15, 0))
        self.environment_combo.bind("<<ComboboxSelected>>", self.on_environment_changed)
        
        # Email field with better spacing
        ttk.Label(login_frame, text="Email:", font=('Segoe UI', 10)).grid(row=1, column=0, sticky="w", pady=(0, 15))
        self.email_var = tk.StringVar()
        self.email_entry = ttk.Entry(login_frame, textvariable=self.email_var, width=50, font=('Segoe UI', 10))
        self.email_entry.grid(row=1, column=1, sticky="ew", pady=(0, 15), padx=(15, 0))
        
        # Password field
        ttk.Label(login_frame, text="Password:", font=('Segoe UI', 10)).grid(row=2, column=0, sticky="w", pady=(0, 20))
        self.password_var = tk.StringVar()
        self.password_entry = ttk.Entry(login_frame, textvariable=self.password_var, show="*", width=50, font=('Segoe UI', 10))
        self.password_entry.grid(row=2, column=1, sticky="ew", pady=(0, 20), padx=(15, 0))
        
        # Buttons frame with better layout
        button_frame = ttk.Frame(login_frame)
        button_frame.grid(row=3, column=0, columnspan=2, pady=(10, 0), sticky="ew")
        
        # Centered button container
        button_container = ttk.Frame(button_frame)
        button_container.pack(expand=True)
        
        # Login button (primary option)
        self.login_button = ttk.Button(button_container, text="Email & Password", command=self.login, style='Primary.TButton')
        self.login_button.pack(side=tk.LEFT, padx=(0, 15), ipadx=10, ipady=5)
        
        # Manual credentials button (secondary option)
        self.manual_button = ttk.Button(button_container, text="Manual Credentials", command=self.show_manual_auth)
        self.manual_button.pack(side=tk.LEFT, ipadx=10, ipady=5)
        
        # Configure grid weights for responsive design
        login_frame.columnconfigure(1, weight=1)
        
        # Bind Enter key to login
        self.email_entry.bind('<Return>', lambda e: self.password_entry.focus())
        self.password_entry.bind('<Return>', lambda e: self.login())
        
        # Status frame with better styling
        status_frame = ttk.LabelFrame(container, text=" 📊 Authentication Status ", padding=25)
        status_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        self.auth_status_text = scrolledtext.ScrolledText(status_frame, height=10, width=80)
        self.auth_status_text.pack(fill=tk.BOTH, expand=True)
        
        # Initial status with environment info
        self.update_environment_status()
        
    def update_environment_status(self):
        """Update the authentication status with current environment info."""
        self.auth_status_text.delete(1.0, tk.END)  # Clear existing text
        
        self.log_auth("🔧 Manual Credentials Authentication")
        self.log_auth("")
        self.log_auth(f"Environment: {self.config.ENVIRONMENT_NAME}")
        self.log_auth(f"🔗 API URL: {self.config.API_BASE_URL}")
        self.log_auth(f"🌐 Web URL: {self.config.WEB_URL}")
        self.log_auth("")
        self.log_auth("📋 RECOMMENDED: Use Manual Credentials")
        self.log_auth("   * 100% reliable with your existing browser session")
        self.log_auth("   * No complex setup needed")  
        self.log_auth("   * Works with all authentication methods")
        self.log_auth("")
        self.log_auth("🔧 Quick Steps:")
        self.log_auth(f"   1. Login at: {self.config.WEB_URL}")
        self.log_auth("   2. Click 'Manual Credentials' button below")
        self.log_auth("   3. Paste your working curl command (auto-extracts tokens)")
        self.log_auth("   4. Or manually copy from browser cookies:")
        self.log_auth("      • F12 → Application → Cookies → _Id, accountId, accessToken")
        self.log_auth("")
        self.log_auth("Email/Password: Available and working")
        
    def on_environment_changed(self, event=None):
        """Handle environment selection change."""
        selected_env = self.environment_var.get()
        self.log_auth(f"🔄 Switching to {selected_env} environment...")
        
        # Update configuration
        self.config.set_environment(selected_env)
        
        # Update auth service with new config
        self.auth_service.config = self.config
        
        # Clear any existing authentication
        self.auth_response = None
        self.organizations = []
        self.locations = []
        self.ap_devices = []
        
        # Update window title and subtitle
        self.root.title(f"AP SDM Port Manager - {self.config.ENVIRONMENT_NAME}")
        
        # Update status display
        self.update_environment_status()
        
        # Reset UI state
        self.connection_status.config(text="⚫ Disconnected", style='Error.TLabel')
        self.user_status.config(text="")
        
        # Clear dropdowns
        if hasattr(self, 'org_combo'):
            self.org_combo.set('')
            self.org_combo['values'] = []
        if hasattr(self, 'loc_combo'):
            self.loc_combo.set('')
            self.loc_combo['values'] = []
            
        # Clear device list if it exists
        if hasattr(self, 'device_tree'):
            for item in self.device_tree.get_children():
                self.device_tree.delete(item)
            if hasattr(self, 'device_map'):
                self.device_map.clear()
        
        # Disable management buttons
        if hasattr(self, 'load_org_button'):
            self.load_org_button.config(state="disabled")
        if hasattr(self, 'share_diagnostics_button'):
            self.share_diagnostics_button.config(state="disabled")
            
        self.log_auth(f"✅ Switched to {self.config.ENVIRONMENT_NAME}")
        
    def setup_management_tab(self):
        """Setup advanced device management tab."""
        mgmt_frame = ttk.Frame(self.notebook)
        self.notebook.add(mgmt_frame, text="🔧 Device Management")
        
        # Create main paned window for resizable layout
        main_paned = ttk.PanedWindow(mgmt_frame, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left panel for controls and filters
        left_panel = ttk.Frame(main_paned)
        main_paned.add(left_panel, weight=1)
        
        # Right panel for device list and details
        right_panel = ttk.Frame(main_paned)  
        main_paned.add(right_panel, weight=3)
        
        # === LEFT PANEL: Controls ===
        self.setup_control_panel(left_panel)
        
        # === RIGHT PANEL: Device Management ===
        self.setup_device_panel(right_panel)
        
    def setup_control_panel(self, parent):
        """Setup the left control panel."""
        # Organization & Location Selection
        selection_frame = ttk.LabelFrame(parent, text=" 🏢 Network Selection ", padding=15)
        selection_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Organization selection
        ttk.Label(selection_frame, text="Organization:", style='Header.TLabel').pack(anchor=tk.W, pady=(0, 5))
        self.org_var = tk.StringVar()
        self.org_combo = ttk.Combobox(selection_frame, textvariable=self.org_var, state="readonly", font=('Segoe UI', 10))
        self.org_combo.pack(fill=tk.X, pady=(0, 10))
        self.org_combo.bind("<<ComboboxSelected>>", self.on_org_selected)
        
        self.load_org_button = ttk.Button(selection_frame, text="🔄 Load Organizations", command=self.load_organizations, state="disabled", style='Primary.TButton')
        self.load_org_button.pack(fill=tk.X, pady=(0, 15), ipady=3)
        
        # Location selection  
        ttk.Label(selection_frame, text="Location:", style='Header.TLabel').pack(anchor=tk.W, pady=(0, 5))
        self.loc_var = tk.StringVar()
        self.loc_combo = ttk.Combobox(selection_frame, textvariable=self.loc_var, state="readonly", font=('Segoe UI', 10))
        self.loc_combo.pack(fill=tk.X, pady=(0, 15))
        self.loc_combo.bind("<<ComboboxSelected>>", self.on_location_selected)
        
        # === DEVICE FILTERS ===
        filter_frame = ttk.LabelFrame(parent, text=" 🔍 Device Filters ", padding=15)
        filter_frame.pack(fill=tk.X, pady=(10, 10))
        
        # Search filter
        ttk.Label(filter_frame, text="Search:").pack(anchor=tk.W)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(filter_frame, textvariable=self.search_var, font=('Segoe UI', 9))
        self.search_entry.pack(fill=tk.X, pady=(2, 10))
        try:
            # Use modern trace_add if available
            self.search_var.trace_add('write', self.on_search_changed)
        except AttributeError:
            # Fallback to older trace method
            self.search_var.trace('w', self.on_search_changed)
        
        # SDM Status filter
        ttk.Label(filter_frame, text="SDM Status:").pack(anchor=tk.W)
        self.filter_var = tk.StringVar(value="All")
        filter_combo = ttk.Combobox(filter_frame, textvariable=self.filter_var, values=["All", "Enabled", "Disabled"], state="readonly", font=('Segoe UI', 9))
        filter_combo.pack(fill=tk.X, pady=(2, 10))
        filter_combo.bind("<<ComboboxSelected>>", self.on_filter_changed)
        
        # Model filter
        ttk.Label(filter_frame, text="Model:").pack(anchor=tk.W)
        self.model_filter_var = tk.StringVar(value="All")
        self.model_filter_combo = ttk.Combobox(filter_frame, textvariable=self.model_filter_var, values=["All"], state="readonly", font=('Segoe UI', 9))
        self.model_filter_combo.pack(fill=tk.X, pady=(2, 0))
        self.model_filter_combo.bind("<<ComboboxSelected>>", self.on_filter_changed)
        
        
        
    def setup_device_panel(self, parent):
        """Setup the right device panel."""
        # === DEVICE LIST ===
        device_list_frame = ttk.LabelFrame(parent, text=" 📋 AP Devices ", padding=15)
        device_list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Toolbar for device actions
        toolbar_frame = ttk.Frame(device_list_frame)
        toolbar_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Check All/None buttons (moved to front)
        self.check_all_button = ttk.Button(toolbar_frame, text="✅ Check All", command=self.check_all_devices, state="disabled")
        self.check_all_button.pack(side=tk.LEFT, padx=(0, 5), ipady=2)
        
        self.check_none_button = ttk.Button(toolbar_frame, text="❌ Check None", command=self.check_none_devices, state="disabled")
        self.check_none_button.pack(side=tk.LEFT, padx=(0, 15), ipady=2)
        
        # Refresh button
        self.refresh_button = ttk.Button(toolbar_frame, text="🔄 Refresh", command=self.refresh_device_status, state="disabled")
        self.refresh_button.pack(side=tk.LEFT, padx=(0, 10), ipady=2)
        
        # Export button
        self.export_button = ttk.Button(toolbar_frame, text="📊 Export", command=self.export_device_data, state="disabled")
        self.export_button.pack(side=tk.LEFT, ipady=2)
        
        # Create frame for enhanced treeview
        tree_container = ttk.Frame(device_list_frame)
        tree_container.pack(fill=tk.BOTH, expand=True)
        
        # Enhanced treeview with selection column
        columns = ("Select", "Name", "Serial", "Model", "IP", "Status", "SDM Status", "SDM Port")
        self.device_tree = ttk.Treeview(tree_container, columns=columns, show="headings", height=15, selectmode='extended')
        
        # Configure columns with selection checkbox
        column_config = {
            "Select": {"width": 60, "anchor": "center"},
            "Name": {"width": 200, "anchor": "w"},
            "Serial": {"width": 150, "anchor": "w"},
            "Model": {"width": 120, "anchor": "w"},
            "IP": {"width": 140, "anchor": "w"},
            "Status": {"width": 100, "anchor": "center"},
            "SDM Status": {"width": 120, "anchor": "center"},
            "SDM Port": {"width": 100, "anchor": "center"}
        }
        
        for col in columns:
            config = column_config[col]
            self.device_tree.heading(col, text=col, anchor=config["anchor"])
            self.device_tree.column(col, width=config["width"], minwidth=60, anchor=config["anchor"])
        
        # Enhanced scrollbars
        v_scrollbar = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.device_tree.yview)
        h_scrollbar = ttk.Scrollbar(tree_container, orient=tk.HORIZONTAL, command=self.device_tree.xview)
        self.device_tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        # Grid layout for scrollbars
        self.device_tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        
        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)
        
        # Bind selection event and double-click for checkbox toggle
        self.device_tree.bind("<<TreeviewSelect>>", self.on_device_selected)
        self.device_tree.bind("<Double-1>", self.toggle_device_selection)
        
        # === SDM CONTROL PANEL (Simple, no tabs) ===
        control_panel = ttk.LabelFrame(parent, text=" ⚙️ SDM Control ", padding=15)
        control_panel.pack(fill=tk.X)
        
        # SDM Controls in a simple horizontal layout
        button_frame = ttk.Frame(control_panel)
        button_frame.pack(expand=True)
        
        self.enable_sdm_button = ttk.Button(button_frame, text="🟢 Enable SDM", command=self.enable_sdm, state="disabled", style='Success.TButton')
        self.enable_sdm_button.pack(side=tk.LEFT, padx=(0, 15), ipadx=20, ipady=8)
        
        self.disable_sdm_button = ttk.Button(button_frame, text="🔴 Disable SDM", command=self.disable_sdm, state="disabled", style='Danger.TButton')
        self.disable_sdm_button.pack(side=tk.LEFT, ipadx=20, ipady=8)
        
        
        
        # Initialize enhanced device management
        self.filtered_devices = []
        self.device_models = set()
        self.device_map = {}  # Map tree item IDs to device objects
        self.selected_devices = set()  # Track selected device serial numbers
        
    def toggle_device_selection(self, event):
        """Toggle device selection when double-clicked."""
        item = self.device_tree.identify_row(event.y)
        if not item:
            return
            
        device = self.get_device_from_item(item)
        if not device:
            return
            
        if device.serialNo in self.selected_devices:
            self.selected_devices.remove(device.serialNo)
            checkbox_status = "☐"
        else:
            self.selected_devices.add(device.serialNo)
            checkbox_status = "☑"
            
        # Update the display
        values = list(self.device_tree.item(item)['values'])
        values[0] = checkbox_status
        self.device_tree.item(item, values=values)
        
        # Update SDM button states
        self.update_bulk_sdm_buttons()
        
    def check_all_devices(self):
        """Select all visible devices."""
        self.selected_devices.clear()
        for item in self.device_tree.get_children():
            device = self.get_device_from_item(item)
            if device:
                self.selected_devices.add(device.serialNo)
                values = list(self.device_tree.item(item)['values'])
                values[0] = "☑"
                self.device_tree.item(item, values=values)
        self.update_bulk_sdm_buttons()
        
    def check_none_devices(self):
        """Deselect all devices."""
        self.selected_devices.clear()
        for item in self.device_tree.get_children():
            values = list(self.device_tree.item(item)['values'])
            values[0] = "☐"
            self.device_tree.item(item, values=values)
        self.update_bulk_sdm_buttons()
        
    def get_selected_devices(self):
        """Get list of currently selected device objects."""
        return [device for device in self.filtered_devices if device.serialNo in self.selected_devices]
        
    def update_bulk_sdm_buttons(self):
        """Update SDM button states based on selection."""
        selected_devices = self.get_selected_devices()
        if selected_devices:
            self.enable_sdm_button.config(state="normal", text=f"🟢 Enable SDM ({len(selected_devices)})")
            self.disable_sdm_button.config(state="normal", text=f"🔴 Disable SDM ({len(selected_devices)})")
        else:
            self.enable_sdm_button.config(state="disabled", text="🟢 Enable SDM")
            self.disable_sdm_button.config(state="disabled", text="🔴 Disable SDM")
        
    def setup_log_tab(self):
        """Setup logging tab."""
        log_frame = ttk.Frame(self.notebook)
        self.notebook.add(log_frame, text="📊 Logs")
        
        # Toolbar for log actions
        log_toolbar = ttk.Frame(log_frame)
        log_toolbar.pack(fill=tk.X, padx=20, pady=(20, 10))
        
        # Share Diagnostics button
        self.share_diagnostics_button = ttk.Button(
            log_toolbar, 
            text="📧 Share Diagnostics", 
            command=self.show_share_diagnostics_modal, 
            state="disabled",
            style='Primary.TButton'
        )
        self.share_diagnostics_button.pack(side=tk.LEFT, ipadx=15, ipady=5)
        
        # Clear logs button
        clear_logs_button = ttk.Button(
            log_toolbar,
            text="🗑️ Clear Logs",
            command=self.clear_logs
        )
        clear_logs_button.pack(side=tk.LEFT, padx=(10, 0), ipadx=10, ipady=5)
        
        # Log text area
        self.log_text = scrolledtext.ScrolledText(log_frame, height=30, width=120)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))
        
        self.log("SDM Manager initialized. Please authenticate to continue.")
        
    def clear_logs(self):
        """Clear all log messages."""
        self.log_text.delete(1.0, tk.END)
        self.log("Logs cleared.")
        
    def log_auth(self, message):
        """Log authentication messages."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.auth_status_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.auth_status_text.see(tk.END)
        self.root.update_idletasks()
        
    def log(self, message):
        """Log general messages."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
        
    def login(self):
        """Handle user login."""
        email = self.email_var.get().strip()
        password = self.password_var.get().strip()
        
        if not email or not password:
            messagebox.showerror("Error", "Please enter both email and password")
            return
        
            
        self.log_auth(f"Authenticating user: {email}")
        self.login_button.config(state="disabled", text="Logging in...")
        
        def auth_thread():
            try:
                self.root.after(0, lambda: self.log_auth("🔄 Trying authentication..."))
                auth_response = self.auth_service.authenticate_user(email, password)
                
                if auth_response and auth_response.success:
                    self.root.after(0, lambda: self.log_auth("✅ Authentication response received"))
                    self.auth_response = auth_response
                    self.root.after(0, self.on_login_success)
                elif auth_response:
                    error_msg = f"Authentication failed: Response received but not successful. User ID: {auth_response.user_id}"
                    self.root.after(0, lambda: self.on_login_error(error_msg))
                else:
                    self.root.after(0, lambda: self.on_login_error("Authentication failed. No valid response received. Please check your credentials and network connection."))
                    
            except Exception as e:
                error_msg = f"Login error: {str(e)}"
                self.root.after(0, lambda: self.on_login_error(error_msg))
        
        threading.Thread(target=auth_thread, daemon=True).start()
        
    def on_login_success(self):
        """Handle successful login."""
        self.log_auth("✅ Authentication successful!")
        
        # Update status indicators
        self.connection_status.config(text="🟢 Connected", style='Success.TLabel')
        self.user_status.config(text=f"👤 {self.auth_response.email}", style='Success.TLabel')
        
        # Determine authentication method used
        auth_method = "Real API Authentication"
        
        if self.auth_response and self.auth_response.token:
            if self.auth_response.token.startswith("session_"):
                auth_method = "Real API (checkuserauth)"
            elif "eyJhbGciOiJ" in self.auth_response.token or len(self.auth_response.token) > 100:
                auth_method = "Real API (JWT Token)"
            elif self.auth_response.token.startswith("authenticated_"):
                auth_method = "Real API (Basic Auth)"
            elif self.auth_response.token.startswith("lookup_token_"):
                auth_method = "Real API (User Lookup)"
            elif self.auth_response.token.startswith("auth_oc_"):
                auth_method = "Real API (authUserFromOC)"
                
        self.log_auth(f"🔐 Authentication Method: {auth_method}")
        self.log_auth(f"User ID: {self.auth_response.user_id}")
        self.log_auth(f"Account ID: {self.auth_response.account_id}")
        self.log_auth(f"Email: {self.auth_response.email}")
        self.log_auth(f"Token: {self.auth_response.token[:30]}...")  # Show more of real token
        self.log_auth("✅ Using live API data from your account")
        
        self.login_button.config(state="normal", text="Email & Password")
        
        # Enable management controls
        self.load_org_button.config(state="normal")
        self.notebook.tab(1, state="normal")  # Enable management tab
        
        # Switch to management tab
        self.notebook.select(1)
        
        self.log("✅ Authentication successful with Real API. You can now load organizations.")
        
        # Auto-load organizations for better UX
        self.root.after(1000, self.load_organizations)  # Load orgs after 1 second
        
    def on_login_error(self, error_message):
        """Handle login error with helpful guidance."""
        self.log_auth(f"❌ {error_message}")
        self.login_button.config(state="normal", text="Email & Password")
        
        # Show helpful guidance instead of just error
        helpful_message = """Email/Password authentication failed.

RECOMMENDED: Use Manual Credentials instead
• 100% reliable with your browser session
• No complex setup needed

Click 'Manual Credentials' button and:
1. Paste your curl command to auto-extract tokens
2. Or manually enter browser cookie values

This method works with your existing authentication!"""
        
        messagebox.showinfo("Use Manual Credentials Instead", helpful_message)
        
    def load_organizations(self):
        """Load organizations for the authenticated user."""
        if not self.auth_response:
            messagebox.showerror("Error", "Please login first")
            return
            
        self.log("Loading organizations...")
        self.load_org_button.config(state="disabled", text="Loading...")
        
        def load_thread():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def fetch_orgs():
                    async with InsightCloudAPI(self.config) as api:
                        return await api.get_organizations(
                            self.auth_response.user_id,
                            self.auth_response.account_id,
                            self.auth_response.token
                        )
                
                organizations = loop.run_until_complete(fetch_orgs())
                loop.close()
                
                self.organizations = organizations
                self.root.after(0, self.update_org_list)
                
            except Exception as e:
                self.root.after(0, lambda error_msg=str(e): self.on_load_error(f"Failed to load organizations: {error_msg}"))
        
        threading.Thread(target=load_thread, daemon=True).start()
        
    def update_org_list(self):
        """Update organization combobox."""
        org_names = [f"{org.orgName} ({org.locationCount} locations)" for org in self.organizations]
        self.org_combo['values'] = org_names
        
        if org_names:
            self.org_combo.set(org_names[0])
            # Auto-load locations for the first organization
            self.root.after(200, self.load_locations)
            
        self.load_org_button.config(state="normal", text="Load Organizations")
        self.log(f"Loaded {len(self.organizations)} organizations")
        
    def on_org_selected(self, event):
        """Handle organization selection."""
        self.loc_combo.set("")
        self.loc_combo['values'] = []
        # Clear device list and selections
        for item in self.device_tree.get_children():
            self.device_tree.delete(item)
        if hasattr(self, 'device_map'):
            self.device_map.clear()
        if hasattr(self, 'selected_devices'):
            self.selected_devices.clear()
        # Auto-load locations for selected organization
        self.root.after(100, self.load_locations)  # Small delay to ensure UI updates
        
    def load_locations(self):
        """Load locations for selected organization."""
        if not self.auth_response or not self.org_combo.get():
            return
            
        selected_index = self.org_combo.current()
        if selected_index < 0:
            return
            
        selected_org = self.organizations[selected_index]
        
        self.log(f"Loading locations for organization: {selected_org.orgName}")
        
        def load_thread():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def fetch_locations():
                    async with InsightCloudAPI(self.config) as api:
                        return await api.get_locations(
                            self.auth_response.user_id,
                            self.auth_response.account_id,
                            self.auth_response.token,
                            selected_org.orgId
                        )
                
                locations = loop.run_until_complete(fetch_locations())
                loop.close()
                
                self.locations = locations
                self.root.after(0, self.update_location_list)
                
            except Exception as e:
                self.root.after(0, lambda error_msg=str(e): self.on_load_error(f"Failed to load locations: {error_msg}"))
        
        threading.Thread(target=load_thread, daemon=True).start()
        
    def update_location_list(self):
        """Update location combobox."""
        loc_names = [f"{loc.networkName} ({loc.apCount} APs)" for loc in self.locations]
        self.loc_combo['values'] = loc_names
        
        if loc_names:
            self.loc_combo.set(loc_names[0])
            # Auto-load devices for the first location
            self.root.after(200, self.load_ap_devices)
            
        self.log(f"Loaded {len(self.locations)} locations")
        
    def on_location_selected(self, event):
        """Handle location selection."""
        # Clear device list and selections
        for item in self.device_tree.get_children():
            self.device_tree.delete(item)
        if hasattr(self, 'device_map'):
            self.device_map.clear()
        if hasattr(self, 'selected_devices'):
            self.selected_devices.clear()
        # Auto-load AP devices for selected location
        self.root.after(100, self.load_ap_devices)  # Small delay to ensure UI updates
        
    def load_ap_devices(self):
        """Load AP devices for selected location."""
        if not self.auth_response or not self.loc_combo.get():
            return
            
        selected_index = self.loc_combo.current()
        if selected_index < 0:
            return
            
        selected_location = self.locations[selected_index]
        
        self.log(f"Loading AP devices for location: {selected_location.networkName}")
        
        def load_thread():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def fetch_devices():
                    async with InsightCloudAPI(self.config) as api:
                        devices = await api.get_ap_devices(
                            self.auth_response.user_id,
                            self.auth_response.account_id,
                            self.auth_response.token,
                            selected_location.networkId
                        )
                        
                        # Get SDM status for each device
                        for device in devices:
                            try:
                                status, port = await api.get_sdm_status(
                                    self.auth_response.user_id,
                                    self.auth_response.account_id,
                                    self.auth_response.token,
                                    device.deviceId,
                                    selected_location.networkId
                                )
                                device.sdmStatus = status
                                device.sdmPort = port
                            except:
                                pass  # Keep default values
                        
                        return devices
                
                devices = loop.run_until_complete(fetch_devices())
                loop.close()
                
                self.ap_devices = devices
                self.selected_location = selected_location
                self.root.after(0, self.update_device_list)
                
            except Exception as e:
                self.root.after(0, lambda error_msg=str(e): self.on_load_error(f"Failed to load AP devices: {error_msg}"))
        
        threading.Thread(target=load_thread, daemon=True).start()
        
    def update_device_list(self):
        """Update device treeview with enhanced display."""
        # Update model filter options
        self.update_model_filter()
        
        # Initialize filters
        self.filtered_devices = self.ap_devices[:]
        
        # Display devices using the enhanced method
        self.display_filtered_devices()
        
        # Enable buttons
        self.refresh_button.config(state="normal")
        self.export_button.config(state="normal")
        self.check_all_button.config(state="normal")
        self.check_none_button.config(state="normal")
        self.share_diagnostics_button.config(state="normal")
        
        self.log(f"✅ Loaded {len(self.ap_devices)} AP devices")
        
    def on_device_selected(self, event):
        """Handle device selection and update details panel."""
        selection = self.device_tree.selection()
        if not selection:
            self.clear_device_details()
            return
            
        item = selection[0]
        device = self.get_device_from_item(item)
        
        if device:
            self.update_device_details(device)
            self.enable_sdm_button.config(state="normal")
            self.disable_sdm_button.config(state="normal")
        else:
            self.clear_device_details()
            
    def update_device_details(self, device):
        """Update device selection for SDM control."""
        # Just enable the SDM buttons since we removed the details display
        pass
            
    def clear_device_details(self):
        """Clear device selection."""
        # Update button states based on current selection
        self.update_bulk_sdm_buttons()
        
    def get_selected_device(self):
        """Get currently selected device (legacy method - now uses bulk selection)."""
        # This method is kept for compatibility but now returns first selected device
        selected_devices = self.get_selected_devices()
        return selected_devices[0] if selected_devices else None
        
    def enable_sdm(self):
        """Enable SDM for selected devices."""
        selected_devices = self.get_selected_devices()
        if not selected_devices:
            messagebox.showwarning("Warning", "Please select at least one device first")
            return
            
        self.log(f"Enabling SDM for {len(selected_devices)} devices...")
        self.enable_sdm_button.config(state="disabled", text="🔄 Enabling...")
        
        def enable_thread():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def enable_sdm_bulk():
                    async with InsightCloudAPI(self.config) as api:
                        results = []
                        for device in selected_devices:
                            try:
                                # Enable SDM
                                success = await api.set_sdm_status(
                                    self.auth_response.user_id,
                                    self.auth_response.account_id,
                                    self.auth_response.token,
                                    device.deviceId,
                                    self.selected_location.networkId,
                                    True
                                )
                                results.append({'device': device, 'success': success, 'port': None})
                                
                                if success:
                                    self.root.after(0, lambda d=device: self.log(f"✅ SDM enabled for {d.name}"))
                                else:
                                    self.root.after(0, lambda d=device: self.log(f"❌ Failed to enable SDM for {d.name}"))
                                    
                            except Exception as e:
                                self.root.after(0, lambda d=device, err=str(e): self.log(f"❌ Error enabling SDM for {d.name}: {err}"))
                                results.append({'device': device, 'success': False, 'port': None})
                                
                        return results
                
                results = loop.run_until_complete(enable_sdm_bulk())
                loop.close()
                
                self.root.after(0, lambda: self.on_bulk_sdm_enabled(results))
                
            except Exception as e:
                self.root.after(0, lambda: self.on_sdm_error(f"Failed to enable SDM: {str(e)}"))
        
        threading.Thread(target=enable_thread, daemon=True).start()
        
    def on_sdm_enabled(self, success, port, device):
        """Handle SDM enable result."""
        self.enable_sdm_button.config(state="normal", text="🟢 Enable SDM")
        
        if success and port:
            self.log(f"✅ SDM enabled for {device.name}! Port: {port}")
            messagebox.showinfo("Success", f"SDM enabled successfully!\nPort: {port}")
        elif success:
            self.log(f"⚠️ SDM enabled for {device.name} but port not available yet")
            messagebox.showwarning("Partial Success", "SDM enabled but port not available yet. Please refresh status in a moment.")
        else:
            self.log(f"❌ Failed to enable SDM for {device.name}")
            messagebox.showerror("Error", "Failed to enable SDM")
            
        # Refresh device list
        self.refresh_device_status()
        
    def disable_sdm(self):
        """Disable SDM for selected devices."""
        selected_devices = self.get_selected_devices()
        if not selected_devices:
            messagebox.showwarning("Warning", "Please select at least one device first")
            return
            
        self.log(f"Disabling SDM for {len(selected_devices)} devices...")
        self.disable_sdm_button.config(state="disabled", text="🔄 Disabling...")
        
        def disable_thread():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def disable_sdm_bulk():
                    async with InsightCloudAPI(self.config) as api:
                        results = []
                        for device in selected_devices:
                            try:
                                success = await api.set_sdm_status(
                                    self.auth_response.user_id,
                                    self.auth_response.account_id,
                                    self.auth_response.token,
                                    device.deviceId,
                                    self.selected_location.networkId,
                                    False
                                )
                                results.append({'device': device, 'success': success})
                                
                                if success:
                                    self.root.after(0, lambda d=device: self.log(f"✅ SDM disabled for {d.name}"))
                                else:
                                    self.root.after(0, lambda d=device: self.log(f"❌ Failed to disable SDM for {d.name}"))
                                    
                            except Exception as e:
                                self.root.after(0, lambda d=device, err=str(e): self.log(f"❌ Error disabling SDM for {d.name}: {err}"))
                                results.append({'device': device, 'success': False})
                                
                        return results
                
                results = loop.run_until_complete(disable_sdm_bulk())
                loop.close()
                
                self.root.after(0, lambda: self.on_bulk_sdm_disabled(results))
                
            except Exception as e:
                self.root.after(0, lambda: self.on_sdm_error(f"Failed to disable SDM: {str(e)}"))
        
        threading.Thread(target=disable_thread, daemon=True).start()
        
    def on_sdm_disabled(self, success, device):
        """Handle SDM disable result."""
        self.disable_sdm_button.config(state="normal", text="🔴 Disable SDM")
        
        if success:
            self.log(f"✅ SDM disabled for {device.name}")
            messagebox.showinfo("Success", "SDM disabled successfully!")
        else:
            self.log(f"❌ Failed to disable SDM for {device.name}")
            messagebox.showerror("Error", "Failed to disable SDM")
            
        # Refresh device list
        self.refresh_device_status()
        
    def on_bulk_sdm_enabled(self, results):
        """Handle bulk SDM enable results."""
        self.update_bulk_sdm_buttons()
        
        successful = [r for r in results if r['success']]
        failed = [r for r in results if not r['success']]
        
        if successful:
            self.log(f"✅ SDM enabled for {len(successful)} devices")
        if failed:
            self.log(f"❌ Failed to enable SDM for {len(failed)} devices")
            
        if len(successful) == len(results):
            messagebox.showinfo("Success", f"SDM enabled for all {len(successful)} devices!")
        elif successful:
            messagebox.showwarning("Partial Success", 
                f"SDM enabled for {len(successful)} devices, failed for {len(failed)} devices")
        else:
            messagebox.showerror("Error", "Failed to enable SDM for all selected devices")
            
        # Refresh device list
        self.refresh_device_status()
        
    def on_bulk_sdm_disabled(self, results):
        """Handle bulk SDM disable results.""" 
        self.update_bulk_sdm_buttons()
        
        successful = [r for r in results if r['success']]
        failed = [r for r in results if not r['success']]
        
        if successful:
            self.log(f"✅ SDM disabled for {len(successful)} devices")
        if failed:
            self.log(f"❌ Failed to disable SDM for {len(failed)} devices")
            
        if len(successful) == len(results):
            messagebox.showinfo("Success", f"SDM disabled for all {len(successful)} devices!")
        elif successful:
            messagebox.showwarning("Partial Success", 
                f"SDM disabled for {len(successful)} devices, failed for {len(failed)} devices")
        else:
            messagebox.showerror("Error", "Failed to disable SDM for all selected devices")
            
        # Refresh device list
        self.refresh_device_status()
        
    def on_sdm_error(self, error_message):
        """Handle SDM operation error."""
        self.update_bulk_sdm_buttons()
        self.log(f"❌ {error_message}")
        messagebox.showerror("Error", error_message)
        
    def refresh_device_status(self):
        """Refresh SDM status for all devices."""
        if not self.ap_devices:
            return
            
        self.log("Refreshing device SDM status...")
        self.refresh_button.config(state="disabled", text="🔄 Refreshing...")
        
        def refresh_thread():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def refresh_async():
                    async with InsightCloudAPI(self.config) as api:
                        for device in self.ap_devices:
                            try:
                                status, port = await api.get_sdm_status(
                                    self.auth_response.user_id,
                                    self.auth_response.account_id,
                                    self.auth_response.token,
                                    device.deviceId,
                                    self.selected_location.networkId
                                )
                                device.sdmStatus = status
                                device.sdmPort = port
                            except:
                                pass
                
                loop.run_until_complete(refresh_async())
                loop.close()
                
                self.root.after(0, self.on_refresh_complete)
                
            except Exception as e:
                self.root.after(0, lambda error_msg=str(e): self.on_load_error(f"Failed to refresh status: {error_msg}"))
        
        threading.Thread(target=refresh_thread, daemon=True).start()
        
    def on_refresh_complete(self):
        """Handle refresh completion."""
        self.update_device_list()
        self.refresh_button.config(state="normal", text="🔄 Refresh")
        self.log("✅ Device status refreshed")
        
    def show_manual_auth(self):
        """Show manual authentication dialog."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Manual Authentication")
        dialog.geometry("550x450")
        dialog.resizable(True, True)
        dialog.minsize(550, 450)
        
        # Center the dialog
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Main frame with proper padding
        main_frame = ttk.Frame(dialog, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        ttk.Label(main_frame, text="Manual Authentication", font=("Arial", 14)).pack(pady=(0, 20))
        
        # Instructions with current environment
        web_domain = self.config.WEB_URL.replace("https://", "")
        instructions_text = f"""To get your credentials:

1. Open {self.config.WEB_URL} in your browser and log in
2. Press F12 → Application → Cookies → {web_domain}
3. Copy these cookie values:
   • _Id → User ID
   • accountId → Account ID  
   • accessToken → Auth Token
4. Paste the values in the fields below

Current Environment: {self.config.ENVIRONMENT_NAME}"""
        
        instructions = ttk.Label(main_frame, text=instructions_text, wraplength=450, justify="left")
        instructions.pack(pady=(0, 10))
        
        
        # Form fields
        fields_frame = ttk.Frame(main_frame)
        fields_frame.pack(fill=tk.X, pady=(10, 0))
        
        # User ID
        ttk.Label(fields_frame, text="User ID:").grid(row=0, column=0, sticky="w", pady=5)
        user_id_var = tk.StringVar()
        user_id_entry = ttk.Entry(fields_frame, textvariable=user_id_var, width=50)
        user_id_entry.grid(row=0, column=1, sticky="ew", pady=5, padx=(10, 0))
        
        # Account ID
        ttk.Label(fields_frame, text="Account ID:").grid(row=1, column=0, sticky="w", pady=5)
        account_id_var = tk.StringVar()
        account_id_entry = ttk.Entry(fields_frame, textvariable=account_id_var, width=50)
        account_id_entry.grid(row=1, column=1, sticky="ew", pady=5, padx=(10, 0))
        
        # Token
        ttk.Label(fields_frame, text="Auth Token:").grid(row=2, column=0, sticky="w", pady=5)
        token_var = tk.StringVar()
        token_entry = ttk.Entry(fields_frame, textvariable=token_var, width=50, show="*")
        token_entry.grid(row=2, column=1, sticky="ew", pady=5, padx=(10, 0))
        
        fields_frame.columnconfigure(1, weight=1)
        
        # Define functions first
        def use_manual_creds():
            user_id = user_id_var.get().strip()
            account_id = account_id_var.get().strip()
            token = token_var.get().strip()
            
            if not all([user_id, account_id, token]):
                messagebox.showerror("Error", "Please fill in all fields")
                return
                
            # Create manual auth response
            self.auth_response = AuthResponse({
                "status": True,
                "data": {
                    "_id": user_id,
                    "email": self.email_var.get(),
                    "accessToken": token
                },
                "accountId": account_id
            })
            
            dialog.destroy()
            self.on_login_success()
            
        def cancel_manual():
            dialog.destroy()
        
        # Add separator line
        separator = ttk.Separator(main_frame, orient='horizontal')
        separator.pack(fill=tk.X, pady=(10, 10))
        
        # Buttons frame - always visible at bottom
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        # Style the primary button
        use_button = ttk.Button(button_frame, text="Use These Credentials", command=use_manual_creds, style='Primary.TButton')
        use_button.pack(side=tk.RIGHT, padx=(0, 10), ipadx=15, ipady=8)
        
        cancel_button = ttk.Button(button_frame, text="Cancel", command=cancel_manual)
        cancel_button.pack(side=tk.RIGHT, ipadx=15, ipady=8)
        
    def show_share_diagnostics_modal(self):
        """Show modal dialog for sharing diagnostics with email addresses."""
        if not self.ap_devices:
            messagebox.showwarning("Warning", "No devices loaded. Please select an organization and location first.")
            return
            
        selected_devices = self.get_selected_devices()
        if not selected_devices:
            messagebox.showwarning("Warning", "Please select at least one device to share diagnostics.")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Share Diagnostics")
        dialog.geometry("650x600")
        dialog.resizable(True, True)
        dialog.minsize(650, 550)
        
        # Center the dialog
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Main frame with proper padding
        main_frame = ttk.Frame(dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Configure main frame grid weights for proper expansion
        main_frame.rowconfigure(2, weight=1)  # Email frame should expand
        
        # Title
        title_label = ttk.Label(main_frame, text="📧 Share Device Diagnostics", font=("Arial", 14, "bold"))
        title_label.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        
        # Device info section
        device_info_frame = ttk.LabelFrame(main_frame, text=" Selected Devices ", padding=15)
        device_info_frame.grid(row=1, column=0, sticky="ew", pady=(0, 15))
        
        device_info_text = scrolledtext.ScrolledText(device_info_frame, height=4, width=60)
        device_info_text.pack(fill=tk.BOTH, expand=True)
        
        # Display selected devices
        for device in selected_devices:
            device_info_text.insert(tk.END, f"• {device.name} ({device.serialNo}) - {device.model}\n")
        device_info_text.config(state=tk.DISABLED)
        
        # Email input section
        email_frame = ttk.LabelFrame(main_frame, text=" Email Recipients ", padding=15)
        email_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        
        # Instructions
        instructions = ttk.Label(email_frame, 
            text="Enter email addresses (one per line) to receive diagnostic information:",
            wraplength=500, justify="left")
        instructions.pack(anchor=tk.W, pady=(0, 10))
        
        # Email text area
        email_text = scrolledtext.ScrolledText(email_frame, height=6, width=60)
        email_text.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Add placeholder text
        email_text.insert(tk.END, "user@example.com\ntech@company.com")
        
        # Validation info
        validation_label = ttk.Label(email_frame, 
            text="📝 Note: Each email address will be validated before sending",
            style='Subtitle.TLabel')
        validation_label.pack(anchor=tk.W)
        
        # Button frame - fixed at bottom
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        
        # Configure main_frame column to expand
        main_frame.columnconfigure(0, weight=1)
        
        # Define button functions
        def send_diagnostics():
            email_content = email_text.get(1.0, tk.END).strip()
            if not email_content:
                messagebox.showerror("Error", "Please enter at least one email address")
                return
                
            # Parse and validate emails
            email_lines = [line.strip() for line in email_content.split('\n') if line.strip()]
            valid_emails = []
            invalid_emails = []
            
            import re
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            
            for email in email_lines:
                if re.match(email_pattern, email):
                    valid_emails.append(email)
                else:
                    invalid_emails.append(email)
            
            if invalid_emails:
                messagebox.showerror("Invalid Email Addresses", 
                    f"The following email addresses are invalid:\n\n" + 
                    "\n".join(invalid_emails[:5]) + 
                    (f"\n... and {len(invalid_emails)-5} more" if len(invalid_emails) > 5 else ""))
                return
            
            if not valid_emails:
                messagebox.showerror("Error", "No valid email addresses found")
                return
            
            dialog.destroy()
            self.share_diagnostics_with_emails(selected_devices, valid_emails)
            
        def cancel_share():
            dialog.destroy()
        
        # Buttons
        send_button = ttk.Button(button_frame, text="📧 Send Diagnostics", 
                               command=send_diagnostics, style='Primary.TButton')
        send_button.pack(side=tk.RIGHT, ipadx=20, ipady=8)
        
        cancel_button = ttk.Button(button_frame, text="Cancel", command=cancel_share)
        cancel_button.pack(side=tk.RIGHT, padx=(0, 10), ipadx=15, ipady=8)
        
        # Focus on email text area and select placeholder text
        email_text.focus_set()
        email_text.tag_add(tk.SEL, "1.0", tk.END)
        email_text.mark_set(tk.INSERT, "1.0")
        
    def share_diagnostics_with_emails(self, devices, email_list):
        """Share diagnostics for selected devices with specified email addresses."""
        if not self.auth_response:
            messagebox.showerror("Error", "Please authenticate first")
            return
            
        if not hasattr(self, 'selected_location') or not self.selected_location:
            messagebox.showerror("Error", "No location selected. Please select a location first")
            return
            
        self.log(f"📧 Sharing diagnostics for {len(devices)} devices with {len(email_list)} recipients...")
        self.share_diagnostics_button.config(state="disabled", text="📧 Sending...")
        
        def share_thread():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def share_diagnostics_bulk():
                    async with InsightCloudAPI(self.config) as api:
                        results = []
                        for device in devices:
                            try:
                                success = await api.share_diagnostics(
                                    self.auth_response.user_id,
                                    self.auth_response.account_id,
                                    self.auth_response.token,
                                    device.deviceId,
                                    self.selected_location.networkId,
                                    email_list
                                )
                                results.append({'device': device, 'success': success})
                                
                                if success:
                                    self.root.after(0, lambda d=device: 
                                        self.log(f"✅ Diagnostics shared for {d.name} ({d.serialNo})"))
                                else:
                                    self.root.after(0, lambda d=device: 
                                        self.log(f"❌ Failed to share diagnostics for {d.name} ({d.serialNo})"))
                                    
                            except Exception as e:
                                self.root.after(0, lambda d=device, err=str(e): 
                                    self.log(f"❌ Error sharing diagnostics for {d.name}: {err}"))
                                results.append({'device': device, 'success': False})
                                
                        return results
                
                results = loop.run_until_complete(share_diagnostics_bulk())
                loop.close()
                
                self.root.after(0, lambda: self.on_diagnostics_shared(results, email_list))
                
            except Exception as e:
                self.root.after(0, lambda: self.on_diagnostics_error(f"Failed to share diagnostics: {str(e)}"))
        
        threading.Thread(target=share_thread, daemon=True).start()
        
    def on_diagnostics_shared(self, results, email_list):
        """Handle diagnostics sharing completion."""
        self.share_diagnostics_button.config(state="normal", text="📧 Share Diagnostics")
        
        successful = [r for r in results if r['success']]
        failed = [r for r in results if not r['success']]
        
        email_recipients = ', '.join(email_list[:3]) + (f' (+{len(email_list)-3} more)' if len(email_list) > 3 else '')
        
        if successful:
            self.log(f"✅ Diagnostics successfully shared for {len(successful)} devices")
            self.log(f"📧 Recipients: {email_recipients}")
        if failed:
            self.log(f"❌ Failed to share diagnostics for {len(failed)} devices")
            
        if len(successful) == len(results):
            messagebox.showinfo("Success", 
                f"Diagnostics successfully shared for all {len(successful)} devices!\n\n"
                f"Recipients: {email_recipients}")
        elif successful:
            messagebox.showwarning("Partial Success", 
                f"Diagnostics shared for {len(successful)} devices, failed for {len(failed)} devices\n\n"
                f"Recipients: {email_recipients}")
        else:
            messagebox.showerror("Error", "Failed to share diagnostics for all selected devices")
            
    def on_diagnostics_error(self, error_message):
        """Handle diagnostics sharing error."""
        self.share_diagnostics_button.config(state="normal", text="📧 Share Diagnostics")
        self.log(f"❌ {error_message}")
        messagebox.showerror("Error", error_message)


    def on_load_error(self, error_message):
        """Handle loading errors."""
        self.log(f"❌ {error_message}")
        messagebox.showerror("Error", error_message)
        
        # Reset button states
        self.load_org_button.config(state="normal", text="Load Organizations")
        
    # === NEW ENHANCED METHODS ===
    
        
        
    def on_search_changed(self, *args):
        """Handle search filter changes."""
        self.apply_filters()
        
    def on_filter_changed(self, *args):
        """Handle filter changes.""" 
        self.apply_filters()
        
    def apply_filters(self):
        """Apply search and filter criteria to device list."""
        if not hasattr(self, 'ap_devices'):
            return
            
        search_text = self.search_var.get().lower()
        status_filter = self.filter_var.get()
        model_filter = self.model_filter_var.get()
        
        # Clear current display and device map
        for item in self.device_tree.get_children():
            self.device_tree.delete(item)
        self.device_map.clear()
        
        self.filtered_devices = []
        
        for device in self.ap_devices:
            # Apply filters
            if search_text and search_text not in device.name.lower() and search_text not in device.serialNo.lower():
                continue
                
            if status_filter != "All":
                sdm_enabled = device.sdmStatus == "1"
                if status_filter == "Enabled" and not sdm_enabled:
                    continue
                elif status_filter == "Disabled" and sdm_enabled:
                    continue
                    
            if model_filter != "All" and device.model != model_filter:
                continue
                
            self.filtered_devices.append(device)
            
        # Display filtered devices
        self.display_filtered_devices()
        
    def display_filtered_devices(self):
        """Display the filtered device list."""
        # Clear existing items and device map first
        for item in self.device_tree.get_children():
            self.device_tree.delete(item)
        self.device_map.clear()
        
        # Add filtered devices
        for device in self.filtered_devices:
            # Format device data for display
            checkbox = "☑" if device.serialNo in self.selected_devices else "☐"
            sdm_status = "🟢 Enabled" if device.sdmStatus == "1" else "🔴 Disabled"
            port = device.sdmPort or "N/A"
            # Fix: deviceStatus is an integer (1=online, 0=offline)
            status = "🟢 Online" if device.deviceStatus == 1 else "🔴 Offline"
            
            item_id = self.device_tree.insert("", tk.END, values=(
                checkbox,
                device.name,
                device.serialNo,
                device.model,
                device.ipAddress or "N/A",
                status,
                sdm_status,
                port
            ))
            
            # Store device reference in our map
            self.device_map[item_id] = device
            
        
    def update_model_filter(self):
        """Update the model filter dropdown with available models."""
        if hasattr(self, 'ap_devices'):
            models = sorted(set(device.model for device in self.ap_devices if device.model))
            self.model_filter_combo['values'] = ["All"] + models
            
    def export_device_data(self):
        """Export device data to CSV."""
        try:
            import csv
            from tkinter import filedialog
            
            if not hasattr(self, 'filtered_devices') or not self.filtered_devices:
                messagebox.showwarning("No Data", "No devices to export")
                return
                
            filename = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                title="Export Device Data"
            )
            
            if filename:
                with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    
                    # Header
                    writer.writerow(["Name", "Serial", "Model", "IP", "Status", "SDM Status", "SDM Port", "MAC Address"])
                    
                    # Data
                    for device in self.filtered_devices:
                        writer.writerow([
                            device.name,
                            device.serialNo,
                            device.model,
                            device.ipAddress or "",
                            "Online" if getattr(device, 'deviceStatus', 0) == 1 else "Offline",
                            "Enabled" if device.sdmStatus == "1" else "Disabled",
                            device.sdmPort or "",
                            getattr(device, 'macAddress', '')
                        ])
                
                messagebox.showinfo("Export Complete", f"Data exported to {filename}")
                
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export data: {str(e)}")
            
        
    def get_device_from_item(self, item):
        """Get device object from tree item."""
        # Get device from our map
        if item in self.device_map:
            return self.device_map[item]
            
        # Fallback: find by serial number from the tree item values
        try:
            serial = self.device_tree.item(item)['values'][2]  # Serial is now at index 2 (after Select and Name)
            for device in self.ap_devices:
                if device.serialNo == serial:
                    return device
        except (IndexError, TypeError):
            pass
            
        return None
        
    def update_device_sdm_display(self, device, new_status):
        """Update device SDM status in the display."""
        device.sdmStatus = new_status
        
        # Find the tree item for this device
        for item_id, mapped_device in self.device_map.items():
            if mapped_device.serialNo == device.serialNo:
                values = list(self.device_tree.item(item_id)['values'])
                values[6] = "🟢 Enabled" if new_status == "1" else "🔴 Disabled"  # SDM Status column (now index 6)
                self.device_tree.item(item_id, values=values)
                break

    def run(self):
        """Start the GUI application."""
        self.root.mainloop()

if __name__ == "__main__":
    print("Starting AP SDM Manager GUI...")
    try:
        app = SDMManagerGUI()
        app.run()
    except KeyboardInterrupt:
        print("\n\nApplication terminated by user")
    except Exception as e:
        print(f"\nUnexpected error: {str(e)}")
        print("Please check your network connection and try again.")
