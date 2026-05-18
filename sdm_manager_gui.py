#!/usr/bin/env python3
import asyncio
import csv
import json
import logging
import os
import posixpath
import re
import shlex
import ssl
import sys
import tempfile
import time
import threading
import uuid
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk
except ImportError as e:
    msg = str(e).lower()
    if "_tkinter" in msg or "tkinter" in msg:
        print(
            "\nThis GUI needs Tcl/Tk. The Python you are using was built without _tkinter.\n\n"
            "On macOS with Homebrew Python 3.14, install the matching Tk bindings:\n"
            "  brew install python-tk@3.14\n\n"
            "Or run with Apple’s system Python (usually has Tk):\n"
            f"  /usr/bin/python3 {Path(__file__).resolve()}\n\n"
            "If the GUI then aborts with “macOS 26 … required, have instead 16 …”, do not use\n"
            "/usr/bin/python3 — use Homebrew python+python-tk or the installer from python.org.\n"
            "On macOS you can run:  ./run_sdm_gui_macos.sh\n",
            file=sys.stderr,
        )
    raise
from dataclasses import replace
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

# File transfer tab: default jump host (SMB Shells).
FT_DEFAULT_JUMP_SSH_URL = "vvdn@smbshells.netgear.com"
# Cap failure lines in batch dialogs so the UI stays responsive with huge batches.
_FT_FAILURE_DIALOG_MAX_LINES = 200

try:
    import aiohttp
    import requests
    import jwt
    import certifi
    from datetime import datetime
except ImportError:
    print("Installing required dependencies...")
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "aiohttp", "requests", "PyJWT", "certifi"])
    import aiohttp
    import requests
    import jwt
    import certifi
    from datetime import datetime

print("SDM Manager: Authentication ready.")

# Verify SSL configuration on startup
try:
    import certifi
    cert_path = certifi.where()
    print(f"✅ SSL certificates loaded from: {cert_path}")
except Exception as e:
    print(f"⚠️ Warning: SSL certificate issue: {e}")
    print("   This may cause SSL verification errors on macOS")

# SSL Configuration Utilities
def get_ssl_context():
    """Create SSL context with proper certificate verification for macOS compatibility."""
    try:
        # Create SSL context with certificate verification
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        print(f"SSL context created with certificate bundle: {certifi.where()}")
        return ssl_context
    except Exception as e:
        print(f"Warning: Could not create SSL context with certifi: {e}")
        try:
            # Fallback to default SSL context
            ssl_context = ssl.create_default_context()
            print("Using default SSL context")
            return ssl_context
        except Exception as e2:
            print(f"Warning: Could not create default SSL context: {e2}")
            return None

def get_ssl_context_no_verify():
    """Create SSL context without verification (for debugging only)."""
    try:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        print("⚠️ Created SSL context without verification (INSECURE - for debugging only)")
        return ssl_context
    except Exception as e:
        print(f"Error creating no-verify SSL context: {e}")
        return None

def get_requests_verify_config(config=None):
    """Get SSL verification configuration for requests library."""
    if config and not config.SSL_VERIFY:
        print("⚠️ SSL verification disabled for requests (INSECURE)")
        return False
        
    try:
        # Use certifi certificate bundle
        cert_bundle = certifi.where()
        print(f"Using certificate bundle for requests: {cert_bundle}")
        return cert_bundle
    except Exception as e:
        print(f"Warning: Could not get certifi bundle: {e}")
        # Fallback to True (use default certificates)
        return True

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
    
    # SSL Configuration - set to False only for debugging SSL issues
    SSL_VERIFY = True  # Set to False to disable SSL verification (NOT recommended for production)
    
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
                timeout=self.config.REQUEST_TIMEOUT,
                verify=get_requests_verify_config(self.config)
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
            error_msg = str(e)
            print(f"Swagger authenticate exception: {error_msg}")
            
            # Provide helpful SSL error guidance
            if "SSL" in error_msg or "certificate" in error_msg.lower():
                print("SSL Certificate Error Detected!")
                print("This is common on macOS. The SSL configuration has been updated to help resolve this.")
                print("If this persists, you can:")
                print("1. Try: pip install --upgrade certifi")
                print("2. Use Manual Credentials authentication instead")
                
            return None
    





# Async API Client
class InsightCloudAPI:
    def __init__(self, config=None):
        self.config = config or Config()
        self.session = None
        
        # Verify SSL setup on initialization
        try:
            ssl_context = get_ssl_context()
            if ssl_context:
                print("✅ SSL context verification successful for API client")
            else:
                print("⚠️ Warning: SSL context could not be created")
        except Exception as e:
            print(f"⚠️ SSL setup warning: {e}")

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=self.config.REQUEST_TIMEOUT)
        
        # Create SSL context based on configuration
        if self.config.SSL_VERIFY:
            ssl_context = get_ssl_context()
            if ssl_context:
                connector = aiohttp.TCPConnector(ssl=ssl_context)
                print("Using SSL-verified aiohttp connector")
            else:
                # If we can't create SSL context but verification is enabled, try default
                connector = aiohttp.TCPConnector()
                print("Warning: Using default aiohttp connector")
        else:
            # SSL verification disabled (for debugging)
            ssl_context = get_ssl_context_no_verify()
            if ssl_context:
                connector = aiohttp.TCPConnector(ssl=ssl_context)
                print("⚠️ Using aiohttp connector WITHOUT SSL verification (INSECURE)")
            else:
                connector = aiohttp.TCPConnector(ssl=False)
                print("⚠️ Using aiohttp connector with SSL disabled (INSECURE)")
        
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector
        )
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
            "apiKey": self.config.API_KEY,     
            "accountId": account_id,      
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
                error_msg = str(e)
                print(f"Request attempt {attempt + 1} failed: {error_msg}")
                
                # Provide helpful SSL error guidance for async requests
                if "SSL" in error_msg or "certificate" in error_msg.lower():
                    print(f"SSL Error in async request to {url}")
                    print("The SSL configuration has been updated to handle certificate verification.")
                
                if attempt == self.config.MAX_RETRIES - 1:
                    # Add more context to SSL errors before raising
                    if "SSL" in error_msg or "certificate" in error_msg.lower():
                        raise Exception(f"SSL Certificate Error: {error_msg}. This has been configured to work with macOS certificate stores.")
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
        self.root.protocol("WM_DELETE_WINDOW", self._on_app_window_close)
        
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

        # File transfer (SSH / sshcommand)
        self.setup_file_transfer_tab()

        # Log tab
        self.setup_log_tab()

        self.notebook.bind("<<NotebookTabChanged>>", self._ft_on_notebook_tab_change)

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
        
        # Log SSL configuration status
        try:
            if self.config.SSL_VERIFY:
                cert_bundle = get_requests_verify_config(self.config)
                if isinstance(cert_bundle, str):
                    self.log(f"✅ SSL certificates configured: {cert_bundle}")
                elif cert_bundle is True:
                    self.log("✅ SSL certificates configured: Using system defaults")
                else:
                    self.log("⚠️ SSL verification disabled")
            else:
                self.log("⚠️ WARNING: SSL verification is DISABLED (insecure mode)")
        except Exception as e:
            self.log(f"⚠️ SSL configuration warning: {e}")
        
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
        if hasattr(self, "_ft_disconnect_all"):
            self._ft_disconnect_all()
        if hasattr(self, "_ft_on_network_context_change"):
            self._ft_on_network_context_change()
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
        if hasattr(self, "_ft_disconnect_all"):
            self._ft_disconnect_all()
        if hasattr(self, "_ft_on_network_context_change"):
            self._ft_on_network_context_change()
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

        if hasattr(self, "_ft_disconnect_all"):
            self._ft_disconnect_all()
        if hasattr(self, "_ft_on_network_context_change"):
            self._ft_on_network_context_change()

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

        if hasattr(self, "_ft_refresh_inventory_from_insight"):
            self._ft_refresh_inventory_from_insight(force=False)

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

    def _ft_on_notebook_tab_change(self, event: tk.Event) -> None:
        try:
            if str(self.notebook.select()) != str(self.ft_tab):
                return
        except Exception:
            return
        if getattr(self, "ft_csv_path", None):
            return
        if hasattr(self, "_ft_refresh_inventory_from_insight"):
            self._ft_refresh_inventory_from_insight(force=False)

    def _ft_clear_csv_for_insight(self) -> None:
        self.ft_csv_path = None
        if hasattr(self, "ft_manual_rows"):
            self.ft_manual_rows.clear()
        self._ft_disconnect_all()
        self._ft_refresh_inventory_from_insight(force=True)
        self._ft_update_summary()
        self._ft_log("CSV cleared; using Insight device list when available.")

    def _ft_show_failures_dialog(self, title: str, lines: List[str]) -> None:
        win = tk.Toplevel(self.root)
        win.title(title)
        win.transient(self.root)
        win.grab_set()
        txt = scrolledtext.ScrolledText(win, width=96, height=22, wrap=tk.WORD)
        txt.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        cap = _FT_FAILURE_DIALOG_MAX_LINES
        if len(lines) > cap:
            head = lines[:cap]
            body = "\n".join(head)
            body += f"\n\n… ({len(lines) - cap} more line(s) omitted; see transfer log.)"
        else:
            body = "\n".join(lines) if lines else "(no detail lines)"
        txt.insert(tk.END, body)
        txt.config(state=tk.DISABLED)
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=8)

    def _ft_reset_download_progress(self) -> None:
        if not hasattr(self, "ft_progress_bar"):
            return

        def _apply() -> None:
            self.ft_progress_bar.config(mode="determinate", maximum=100, value=0)
            self.ft_progress_label.config(text="")

        self.root.after(0, _apply)

    def _ft_set_download_progress(self, cur: int, total: int, msg: str) -> None:
        def _apply() -> None:
            if not hasattr(self, "ft_progress_bar"):
                return
            mx = max(int(total), 1)
            self.ft_progress_bar.config(mode="determinate", maximum=mx, value=min(int(cur), mx))
            self.ft_progress_label.config(text=msg)

        self.root.after(0, _apply)

    def _ft_insight_inventory_key(self) -> Optional[str]:
        if getattr(self, "ft_csv_path", None):
            return None
        loc = getattr(self, "selected_location", None)
        devs = getattr(self, "ap_devices", None)
        if loc is None or devs is None:
            return None
        parts: List[tuple] = []
        for d in devs:
            parts.append(
                (
                    getattr(d, "serialNo", "") or "",
                    getattr(d, "deviceId", "") or "",
                    d.name or "",
                    str(d.sdmPort) if d.sdmPort is not None else "",
                    str(getattr(d, "sdmStatus", "")),
                )
            )
        parts.sort()
        nid = str(getattr(loc, "networkId", "") or "")
        return f"{nid}\x1e{json.dumps(parts, separators=(',', ':'))}"

    def _ft_invalidate_insight_snapshot(self) -> None:
        self._ft_last_insight_inventory_key = None

    def _ft_on_network_context_change(self) -> None:
        self._ft_invalidate_insight_snapshot()
        if not hasattr(self, "ft_manual_rows"):
            return
        self.ft_manual_rows.clear()
        if getattr(self, "ft_csv_path", None):
            return
        if not hasattr(self, "ft_inventory"):
            return
        for e in list(self.ft_inventory):
            if e.get("manual") and self.ft_tree.exists(e["iid"]):
                self.ft_tree.delete(e["iid"])
        self.ft_inventory = [e for e in self.ft_inventory if not e.get("manual")]
        self._ft_update_inventory_status_message()
        self._ft_sync_run_button_state()

    def _ft_display_name(self, raw: Dict[str, str]) -> str:
        n = (raw.get("Name") or "").strip()
        return n if n else "(unnamed)"

    def _ft_update_inventory_status_message(self) -> None:
        if getattr(self, "ft_csv_path", None):
            return
        if not hasattr(self, "ft_inventory"):
            return
        n_ins = sum(1 for e in self.ft_inventory if not e.get("manual"))
        n_man = sum(1 for e in self.ft_inventory if e.get("manual"))
        n_elig = sum(1 for e in self.ft_inventory if e["eligible"])
        if not getattr(self, "auth_response", None):
            msg = (
                "Authenticate to load Insight APs. You can use Add port for manual jump sessions "
                "or browse a CSV (SDM Port column required)."
            )
        elif not getattr(self, "ap_devices", None):
            msg = f"Manual rows: {n_man}; selectable (valid SDM port)={n_elig}. Load APs for the Insight list."
        else:
            msg = f"Insight: {n_ins} AP(s), manual={n_man}, selectable (valid SDM port)={n_elig}."
        self.ft_csv_label_var.set(msg)

    def _ft_insert_manual_row_live(self, sc: Any, iid: str, raw: Dict[str, str]) -> None:
        port_ok = sc.is_valid_sdm_port((raw.get("SDM Port") or "")) is not None
        eligible = port_ok
        self.ft_inventory.append({"iid": iid, "raw": raw, "eligible": eligible, "manual": True})
        dn = self._ft_display_name(raw)
        self.ft_tree.insert(
            "",
            tk.END,
            iid=iid,
            values=(
                "☐",
                dn,
                raw.get("IP", "") or "",
                raw.get("Model", "") or "",
                raw.get("SDM Status", "") or "",
                raw.get("SDM Port", "") or "",
                "—" if not eligible else "Disconnected",
            ),
        )
        self._ft_update_inventory_status_message()
        self._ft_sync_run_button_state()

    def _ft_refresh_inventory_from_insight(self, force: bool = False) -> None:
        """Rebuild File transfer tree from Insight API devices when no CSV is active."""
        if getattr(self, "ft_csv_path", None):
            return
        key = self._ft_insight_inventory_key()
        last = getattr(self, "_ft_last_insight_inventory_key", None)
        if not force and key is not None and last == key:
            return
        try:
            sc = self._ft_import_sshcommand()
        except Exception as exc:
            self.ft_csv_label_var.set(f"Could not load sshcommand: {exc}")
            return

        self.ft_csv_fieldnames = ["Name", "SDM Port", "SDM Status", "IP", "Model"]
        for it in self.ft_tree.get_children():
            self.ft_tree.delete(it)
        self.ft_inventory = []

        if getattr(self, "auth_response", None) and getattr(self, "ap_devices", None):
            for i, device in enumerate(self.ap_devices):
                port_str = "" if device.sdmPort is None else str(device.sdmPort)
                sdm_st = "Enabled" if str(device.sdmStatus) == "1" else "Disabled"
                port_ok = sc.is_valid_sdm_port(port_str) is not None
                eligible = port_ok
                raw: Dict[str, str] = {
                    "Name": device.name or "",
                    "SDM Port": port_str,
                    "SDM Status": sdm_st,
                    "IP": device.ipAddress or "",
                    "Model": device.model or "",
                }
                iid = str(i)
                self.ft_inventory.append({"iid": iid, "raw": raw, "eligible": eligible, "manual": False})
                dn = self._ft_display_name(raw)
                self.ft_tree.insert(
                    "",
                    tk.END,
                    iid=iid,
                    values=(
                        "☐",
                        dn,
                        raw["IP"],
                        raw["Model"],
                        raw["SDM Status"],
                        raw["SDM Port"],
                        "—" if not eligible else "Disconnected",
                    ),
                )

        for m in list(getattr(self, "ft_manual_rows", [])):
            iid_m = m["iid"]
            raw_m = dict(m["raw"])
            port_ok = sc.is_valid_sdm_port((raw_m.get("SDM Port") or "")) is not None
            eligible = port_ok
            self.ft_inventory.append({"iid": iid_m, "raw": raw_m, "eligible": eligible, "manual": True})
            dn = self._ft_display_name(raw_m)
            self.ft_tree.insert(
                "",
                tk.END,
                iid=iid_m,
                values=(
                    "☐",
                    dn,
                    raw_m.get("IP", "") or "",
                    raw_m.get("Model", "") or "",
                    raw_m.get("SDM Status", "") or "",
                    raw_m.get("SDM Port", "") or "",
                    "—" if not eligible else "Disconnected",
                ),
            )

        self._ft_last_insight_inventory_key = key
        self._ft_update_inventory_status_message()
        self._ft_sync_run_button_state()

    def _ft_import_sshcommand(self):
        """Load sshCommander/sshcommand.py as ``sshcommand``."""
        root = Path(__file__).resolve().parent / "sshCommander"
        p = str(root)
        if p not in sys.path:
            sys.path.insert(0, p)
        import sshcommand  # noqa: PLC0415

        return sshcommand

    def setup_file_transfer_tab(self):
        """Tab: CSV AP pick, batch or single-AP explorer upload/download via sshcommand."""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="📁 File transfer")
        self.ft_tab = tab

        self.ft_csv_path: Optional[Path] = None
        self.ft_csv_fieldnames: List[str] = []
        self.ft_inventory: List[Dict[str, Any]] = []
        self.ft_manual_rows: List[Dict[str, Any]] = []
        self._ft_last_insight_inventory_key: Optional[str] = None
        self.ft_batch_upload_paths: List[Path] = []
        self.ft_local_cwd = Path.home().resolve()
        self.ft_busy = False
        self.ft_action_widgets: List[tk.Widget] = []

        ft_canvas = tk.Canvas(tab, highlightthickness=0)
        ft_scroll = ttk.Scrollbar(tab, orient=tk.VERTICAL, command=ft_canvas.yview)
        ft_inner = ttk.Frame(ft_canvas)
        ft_win = ft_canvas.create_window((0, 0), window=ft_inner, anchor="nw")

        def _ft_inner_configure(_: tk.Event) -> None:
            ft_canvas.configure(scrollregion=ft_canvas.bbox("all"))

        def _ft_canvas_configure(e: tk.Event) -> None:
            ft_canvas.itemconfigure(ft_win, width=e.width)

        ft_inner.bind("<Configure>", _ft_inner_configure)
        ft_canvas.bind("<Configure>", _ft_canvas_configure)
        ft_canvas.configure(yscrollcommand=ft_scroll.set)
        ft_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        ft_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        def _ft_canvas_mousewheel(event: tk.Event) -> Optional[str]:
            if getattr(event, "delta", 0):
                ft_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            elif getattr(event, "num", 0) == 4:
                ft_canvas.yview_scroll(-3, "units")
            elif getattr(event, "num", 0) == 5:
                ft_canvas.yview_scroll(3, "units")
            return "break"

        ft_canvas.bind("<MouseWheel>", _ft_canvas_mousewheel)
        ft_canvas.bind("<Button-4>", _ft_canvas_mousewheel)
        ft_canvas.bind("<Button-5>", _ft_canvas_mousewheel)
        ft_inner.bind("<MouseWheel>", _ft_canvas_mousewheel)
        ft_inner.bind("<Button-4>", _ft_canvas_mousewheel)
        ft_inner.bind("<Button-5>", _ft_canvas_mousewheel)

        self.ft_tab_canvas = ft_canvas

        self.ft_main_col = ttk.Frame(ft_inner)
        self.ft_main_col.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        top_area = ttk.Frame(self.ft_main_col)
        top_area.pack(fill=tk.BOTH, expand=True)

        jump = ttk.LabelFrame(top_area, text=" Jump host (SMB Shells) ", padding=10)
        jump.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(
            jump,
            text="Uses sshcommand with --accept-new-host-key (always on). Batches use rows with a valid SDM port (SDM does not need to show Enabled).",
            wraplength=720,
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

        self.ft_url_var = tk.StringVar(value=FT_DEFAULT_JUMP_SSH_URL)
        self.ft_rsa_var = tk.StringVar()
        self.ft_ssh_port_var = tk.StringVar(value="443")
        ttk.Label(jump, text="SSH URL (user@host):").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Entry(jump, textvariable=self.ft_url_var, width=48).grid(row=1, column=1, sticky="ew", padx=6)
        ttk.Label(jump, text="SSH key (-i):").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Entry(jump, textvariable=self.ft_rsa_var, width=48).grid(row=2, column=1, sticky="ew", padx=6)
        ttk.Button(jump, text="Browse…", command=self._ft_browse_rsa).grid(row=2, column=2, padx=4)
        ttk.Label(jump, text="Jump SSH port:").grid(row=3, column=0, sticky="w", pady=2)
        ttk.Entry(jump, textvariable=self.ft_ssh_port_var, width=8).grid(row=3, column=1, sticky="w", padx=6)
        jump.columnconfigure(1, weight=1)

        rel = ttk.LabelFrame(top_area, text=" Connection reliability (serial) ", padding=8)
        rel.pack(fill=tk.X, pady=(0, 8))
        r1 = ttk.Frame(rel)
        r1.pack(fill=tk.X)
        self.ft_rel_extra_retries_var = tk.StringVar(value="2")
        self.ft_rel_backoff_var = tk.StringVar(value="0.5")
        self.ft_rel_pause_connect_var = tk.StringVar(value="0.2")
        self.ft_rel_pause_batch_var = tk.StringVar(value="0.15")
        ttk.Label(r1, text="Extra connect retries:").pack(side=tk.LEFT)
        ttk.Entry(r1, textvariable=self.ft_rel_extra_retries_var, width=4).pack(side=tk.LEFT, padx=(4, 12))
        ttk.Label(r1, text="Backoff base (s):").pack(side=tk.LEFT)
        ttk.Entry(r1, textvariable=self.ft_rel_backoff_var, width=6).pack(side=tk.LEFT, padx=(4, 12))
        ttk.Label(r1, text="Pause after connect (s):").pack(side=tk.LEFT)
        ttk.Entry(r1, textvariable=self.ft_rel_pause_connect_var, width=6).pack(side=tk.LEFT, padx=(4, 12))
        ttk.Label(r1, text="Pause between batch APs (s):").pack(side=tk.LEFT)
        ttk.Entry(r1, textvariable=self.ft_rel_pause_batch_var, width=6).pack(side=tk.LEFT, padx=(4, 0))
        r2 = ttk.Frame(rel)
        r2.pack(fill=tk.X, pady=(6, 0))
        self.ft_rel_ping_var = tk.BooleanVar(value=False)
        self.ft_rel_batch_reconnect_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(r2, text="Ping shell after connect", variable=self.ft_rel_ping_var).pack(
            side=tk.LEFT, padx=(0, 16)
        )
        ttk.Checkbutton(
            r2,
            text="Reconnect if session dead before batch",
            variable=self.ft_rel_batch_reconnect_var,
        ).pack(side=tk.LEFT)

        csv_frame = ttk.LabelFrame(top_area, text=" 1. Inventory (CSV or Insight) ", padding=10)
        csv_frame.pack(fill=tk.X, pady=(0, 8))
        self.ft_csv_label_var = tk.StringVar(value="No CSV loaded")
        csv_btn_row = ttk.Frame(csv_frame)
        csv_btn_row.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(csv_btn_row, text="Browse CSV…", command=self._ft_browse_csv).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(csv_btn_row, text="Clear CSV", command=self._ft_clear_csv_for_insight).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(csv_frame, textvariable=self.ft_csv_label_var, wraplength=720).pack(fill=tk.X, anchor=tk.W)
        ttk.Label(
            csv_frame,
            text="CSV must include SDM Port (Name optional; added if missing). Without CSV, the list follows Device Management when APs are loaded; use Add port for a jump session by port only.",
            wraplength=720,
            foreground="#555",
        ).pack(fill=tk.X, pady=(8, 0))

        ap_frame = ttk.LabelFrame(top_area, text=" 2. Select APs ", padding=10)
        ap_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        tb = ttk.Frame(ap_frame)
        tb.pack(fill=tk.X, pady=(0, 6))
        ttk.Button(tb, text="Select all (valid port)", command=self._ft_check_all).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(tb, text="Clear selection", command=self._ft_check_none).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(tb, text="Add port…", command=self._ft_add_manual_port_clicked).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(tb, text="Remove", command=self._ft_remove_manual_port_clicked).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(tb, text="Connect", command=self._ft_connect_clicked).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(tb, text="Disconnect", command=self._ft_disconnect_all).pack(side=tk.LEFT)
        self.ft_sel_count_var = tk.StringVar(value="Selected APs (valid port): 0")
        ttk.Label(tb, textvariable=self.ft_sel_count_var).pack(side=tk.RIGHT)

        tree_wrap = ttk.Frame(ap_frame)
        tree_wrap.pack(fill=tk.BOTH, expand=True)
        cols = ("Select", "Name", "IP", "Model", "SDM Status", "SDM Port", "Connection")
        self.ft_tree = ttk.Treeview(tree_wrap, columns=cols, show="headings", height=6, selectmode="browse")
        for c, w in zip(cols, (50, 160, 110, 90, 90, 80, 100)):
            self.ft_tree.heading(c, text=c)
            self.ft_tree.column(
                c,
                width=w,
                anchor=tk.CENTER if c in ("Select", "SDM Port", "Connection") else tk.W,
            )
        vsb = ttk.Scrollbar(tree_wrap, orient=tk.VERTICAL, command=self.ft_tree.yview)
        self.ft_tree.configure(yscrollcommand=vsb.set)
        self.ft_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        tree_wrap.grid_rowconfigure(0, weight=1)
        tree_wrap.grid_columnconfigure(0, weight=1)
        self.ft_tree.bind("<Double-1>", self._ft_toggle_row)
        self.ft_tree.bind("<<TreeviewSelect>>", lambda e: self._ft_on_tree_select())

        mode_fr = ttk.LabelFrame(top_area, text=" 3. Transfer mode ", padding=10)
        mode_fr.pack(fill=tk.X, pady=(0, 8))
        mode_row = ttk.Frame(mode_fr)
        mode_row.pack(fill=tk.X)
        self.ft_mode_var = tk.StringVar(value="upload")
        ttk.Radiobutton(mode_row, text="Upload", variable=self.ft_mode_var, value="upload", command=self._ft_on_mode_change).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Radiobutton(mode_row, text="Download", variable=self.ft_mode_var, value="download", command=self._ft_on_mode_change).pack(side=tk.LEFT)
        to_row = ttk.Frame(mode_fr)
        to_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(to_row, text="Download timeout (sec, base64 wait per file):").pack(side=tk.LEFT)
        self.ft_download_timeout_var = tk.StringVar(value="900")
        ttk.Entry(to_row, textvariable=self.ft_download_timeout_var, width=10).pack(side=tk.LEFT, padx=6)

        self.ft_body = ttk.Frame(self.ft_main_col)
        self.ft_body.pack(fill=tk.BOTH, expand=True)

        self.ft_batch_frame = ttk.LabelFrame(self.ft_body, text=" Batch (multiple APs) ", padding=10)
        self.ft_batch_frame.pack(fill=tk.BOTH, expand=True)

        self.ft_batch_row1 = ttk.Frame(self.ft_batch_frame)
        self.ft_batch_row1.pack(fill=tk.X, pady=4)
        self.ft_batch_path_label = ttk.Label(self.ft_batch_row1, text="Destination on APs:")
        self.ft_batch_path_label.pack(anchor=tk.W)
        self.ft_batch_ap_path_var = tk.StringVar()
        self.ft_batch_path_entry = ttk.Entry(self.ft_batch_row1, textvariable=self.ft_batch_ap_path_var, width=70)
        self.ft_batch_path_entry.pack(fill=tk.X, pady=2)

        self.ft_batch_row2 = ttk.Frame(self.ft_batch_frame)
        self.ft_batch_row2.pack(fill=tk.X, pady=4)
        self.ft_batch_local_label = ttk.Label(self.ft_batch_row2, text="Local files:")
        self.ft_batch_local_label.pack(anchor=tk.W)
        br = ttk.Frame(self.ft_batch_row2)
        br.pack(fill=tk.X)
        ttk.Button(br, text="Browse files…", command=self._ft_browse_batch_upload_files).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(br, text="Clear file list", command=self._ft_clear_batch_files).pack(side=tk.LEFT, padx=(0, 8))
        self.ft_upload_binary_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(br, text="Binary (chmod +x after upload)", variable=self.ft_upload_binary_var).pack(side=tk.LEFT)
        self.ft_batch_files_list = tk.Listbox(self.ft_batch_frame, height=4, selectmode=tk.EXTENDED)
        self.ft_batch_files_list.pack(fill=tk.BOTH, expand=True, pady=4)

        self.ft_batch_dl_row = ttk.Frame(self.ft_batch_frame)
        ttk.Label(
            self.ft_batch_dl_row,
            text="Remote file paths on APs (one per line; same list for every selected AP):",
        ).pack(anchor=tk.W)
        self.ft_batch_remote_paths_text = scrolledtext.ScrolledText(
            self.ft_batch_dl_row, height=4, width=70, wrap=tk.NONE
        )
        self.ft_batch_remote_paths_text.pack(fill=tk.BOTH, expand=True, pady=2)
        ttk.Label(self.ft_batch_dl_row, text="Local folder (each AP gets a subfolder):").pack(anchor=tk.W, pady=(6, 0))
        dl_b = ttk.Frame(self.ft_batch_dl_row)
        dl_b.pack(fill=tk.X)
        self.ft_batch_local_dir_var = tk.StringVar()
        ttk.Entry(dl_b, textvariable=self.ft_batch_local_dir_var, width=55).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(dl_b, text="Browse…", command=self._ft_browse_batch_local_dir).pack(side=tk.LEFT, padx=6)

        self.ft_explorer_frame = ttk.LabelFrame(self.ft_body, text=" Single AP browser ", padding=8)
        ttk.Label(
            self.ft_explorer_frame,
            text="Large files may be slow (base64 over shell).",
            foreground="#666",
        ).pack(anchor=tk.W, pady=(0, 6))

        exp_grid = ttk.Frame(self.ft_explorer_frame)
        exp_grid.pack(fill=tk.BOTH, expand=True)
        self.ft_remote_cwd_var = tk.StringVar(value="/tmp")
        loc_lab = ttk.LabelFrame(exp_grid, text=" Local ", padding=6)
        rem_lab = ttk.LabelFrame(exp_grid, text=" Remote (AP) ", padding=6)
        loc_lab.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        rem_lab.grid(row=0, column=1, sticky="nsew")
        exp_grid.columnconfigure(0, weight=1)
        exp_grid.columnconfigure(1, weight=1)
        exp_grid.rowconfigure(0, weight=1)

        lf_top = ttk.Frame(loc_lab)
        lf_top.pack(fill=tk.X)
        self.ft_local_cwd_var = tk.StringVar(value=str(self.ft_local_cwd))
        ttk.Entry(lf_top, textvariable=self.ft_local_cwd_var, width=40).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(lf_top, text="Go", command=self._ft_local_go).pack(side=tk.LEFT, padx=4)
        ttk.Button(lf_top, text="Refresh", command=self._ft_refresh_local_list).pack(side=tk.LEFT)
        self.ft_local_list = tk.Listbox(loc_lab, selectmode=tk.EXTENDED, height=10)
        self.ft_local_list.pack(fill=tk.BOTH, expand=True, pady=4)
        self.ft_local_list.bind("<Double-1>", self._ft_local_double_click)

        rf_top = ttk.Frame(rem_lab)
        rf_top.pack(fill=tk.X)
        ttk.Entry(rf_top, textvariable=self.ft_remote_cwd_var, width=40).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(rf_top, text="Go", command=self._ft_remote_go).pack(side=tk.LEFT, padx=4)
        self.ft_remote_refresh_btn = ttk.Button(rf_top, text="Refresh", command=self._ft_refresh_remote_list)
        self.ft_remote_refresh_btn.pack(side=tk.LEFT)
        self.ft_remote_list = tk.Listbox(rem_lab, selectmode=tk.EXTENDED, height=10)
        self.ft_remote_list.pack(fill=tk.BOTH, expand=True, pady=4)
        self.ft_remote_list.bind("<Double-1>", self._ft_remote_double_click)

        ex_btn = ttk.Frame(self.ft_explorer_frame)
        ex_btn.pack(fill=tk.X, pady=6)
        ttk.Button(ex_btn, text="Upload selected → AP", command=self._ft_explorer_upload).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Checkbutton(
            ex_btn,
            text="Binary (+x)",
            variable=self.ft_upload_binary_var,
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(ex_btn, text="Download selected ← AP", command=self._ft_explorer_download).pack(side=tk.LEFT)

        self.ft_explorer_frame.pack_forget()

        log_fr = ttk.LabelFrame(self.ft_main_col, text=" Transfer log ", padding=8)
        log_fr.pack(fill=tk.BOTH, expand=True)
        self.ft_log_text = scrolledtext.ScrolledText(log_fr, height=8, wrap=tk.WORD)
        self.ft_log_text.pack(fill=tk.BOTH, expand=True)
        ttk.Button(log_fr, text="Clear log", command=self._ft_clear_log).pack(anchor=tk.E, pady=(4, 0))

        self.ft_actions = ttk.LabelFrame(self.ft_main_col, text=" Transfer actions ", padding=8)
        self.ft_actions.pack(fill=tk.X, pady=(8, 0))
        act_row = ttk.Frame(self.ft_actions)
        act_row.pack(fill=tk.X)
        self.ft_run_btn = ttk.Button(act_row, text="Run transfer", command=self._ft_run_transfer, style="Primary.TButton")
        self.ft_run_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.ft_stop_btn = ttk.Button(act_row, text="Stop transfer", command=self._ft_stop_transfer, state=tk.DISABLED)
        self.ft_stop_btn.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(act_row, text="Clear form", command=self._ft_clear_form).pack(side=tk.LEFT)
        prog_row = ttk.Frame(self.ft_actions)
        prog_row.pack(fill=tk.X, pady=(8, 0))
        self.ft_progress_label = ttk.Label(prog_row, text="")
        self.ft_progress_label.pack(anchor=tk.W)
        self.ft_progress_bar = ttk.Progressbar(prog_row, mode="determinate", maximum=100, value=0)
        self.ft_progress_bar.pack(fill=tk.X, pady=(4, 0))

        self.ft_action_widgets.extend([self.ft_run_btn, self.ft_stop_btn, self.ft_remote_refresh_btn, self.ft_explorer_frame])
        self.ft_sessions: Dict[str, Any] = {}
        self.ft_session_locks: Dict[str, threading.Lock] = {}
        self.ft_transfer_cancel_event = threading.Event()
        self.ft_connect_cancel_event = threading.Event()
        self._ft_transfer_state_lock = threading.Lock()
        self._ft_transfer_active_child: Any = None
        self._ft_transfer_active_iid: Optional[str] = None

        self._ft_on_mode_change()
        self._ft_update_selection_layout()
        self._ft_sync_run_button_state()
        self._ft_refresh_inventory_from_insight(force=True)

    def _on_app_window_close(self) -> None:
        try:
            self._ft_disconnect_all()
        except Exception:
            pass
        self.root.destroy()

    def _ft_lock_for(self, iid: str) -> threading.Lock:
        if iid not in self.ft_session_locks:
            self.ft_session_locks[iid] = threading.Lock()
        return self.ft_session_locks[iid]

    def _ft_parse_download_timeout_sec(self) -> float:
        raw = (self.ft_download_timeout_var.get() or "").strip()
        try:
            v = int(float(raw))
        except ValueError:
            raise ValueError("invalid")
        if v < 30 or v > 86400:
            raise ValueError("range")
        return float(v)

    def _ft_begin_transfer_ops(self, iid: str, child: Any) -> None:
        with self._ft_transfer_state_lock:
            self._ft_transfer_active_iid = iid
            self._ft_transfer_active_child = child

    def _ft_end_transfer_ops(self) -> None:
        with self._ft_transfer_state_lock:
            self._ft_transfer_active_child = None
            self._ft_transfer_active_iid = None

    def _ft_stop_transfer(self) -> None:
        self.ft_transfer_cancel_event.set()
        ch: Any = None
        iid: Optional[str] = None
        with self._ft_transfer_state_lock:
            ch = self._ft_transfer_active_child
            iid = self._ft_transfer_active_iid
        if ch is not None:
            try:
                ch.close(force=True)
            except Exception:
                pass
        if iid:
            lk = self._ft_lock_for(iid)
            with lk:
                self.ft_sessions.pop(iid, None)
            self._ft_set_conn_status(iid, "Disconnected")
        self._ft_log("Stop: transfer interrupted (session closed; reconnect if needed).")

    def _ft_set_conn_status(self, iid: str, text: str) -> None:
        if not self.ft_tree.exists(iid):
            return
        vals = list(self.ft_tree.item(iid)["values"])
        while len(vals) < 7:
            vals.append("Disconnected")
        vals[6] = text
        self.ft_tree.item(iid, values=tuple(vals))

    def _ft_parse_rel_int(self, sv: tk.StringVar, default: int, lo: int, hi: int) -> int:
        try:
            v = int((sv.get() or "").strip())
        except ValueError:
            return default
        return max(lo, min(hi, v))

    def _ft_parse_rel_seconds(self, sv: tk.StringVar, default: float, lo: float, hi: float) -> float:
        try:
            v = float((sv.get() or "").strip())
        except ValueError:
            return default
        return max(lo, min(hi, v))

    def _ft_is_transient_connect_error(self, err: str) -> bool:
        if not err or err.strip().lower() == "cancelled":
            return False
        el = err.lower()
        if "cancelled" in el:
            return False
        needles = (
            "timeout",
            "unexpected eof",
            "milestone=port_prompt",
            "milestone=device_shell",
            "milestone=attach",
            "ping:",
        )
        return any(n in el for n in needles)

    def _ft_shell_alive(self, ch: Any) -> bool:
        if ch is None:
            return False
        try:
            if getattr(ch, "closed", False):
                return False
        except Exception:
            pass
        try:
            if hasattr(ch, "isalive") and not ch.isalive():
                return False
        except Exception:
            pass
        return True

    def _ft_raw_for_iid(self, iid: str) -> Optional[Dict[str, str]]:
        for ent in self.ft_inventory:
            if ent["iid"] == iid:
                return ent["raw"]
        return None

    def _ft_force_close_child(self, sc: Any, ch: Any) -> None:
        if ch is None:
            return
        try:
            if sc is not None:
                sc.detach_device_shell(ch, 45.0, lambda _m: None)
        except Exception:
            pass
        try:
            ch.close(force=True)
        except Exception:
            pass

    def _ft_ensure_batch_channel(
        self,
        sc: Any,
        ssh_cmd: List[str],
        iid: str,
        tag: str,
        failures: List[str],
        log_cb: Callable[[str], None],
    ) -> Any:
        lk = self._ft_lock_for(iid)
        with lk:
            ch = self.ft_sessions.get(iid)
        if self._ft_shell_alive(ch):
            return ch
        had = ch is not None
        if had:
            with lk:
                if self.ft_sessions.get(iid) is ch:
                    self.ft_sessions.pop(iid, None)
            self._ft_force_close_child(sc, ch)
        if not self.ft_rel_batch_reconnect_var.get():
            if not had:
                failures.append(f"{tag} Connect first (skipped).")
            else:
                failures.append(f"{tag} session dead (enable 'Reconnect…' or Connect again).")
            return None
        raw = self._ft_raw_for_iid(iid)
        if raw is None:
            failures.append(f"{tag} session dead; no table row for reconnect.")
            return None
        port = sc.is_valid_sdm_port(raw.get("SDM Port") or "")
        if port is None:
            failures.append(f"{tag} session dead; invalid port for reconnect.")
            return None
        if self.ft_transfer_cancel_event.is_set():
            return None
        log_cb("milestone: reconnecting dead session")
        child, err = sc.attach_device_shell(
            ssh_cmd,
            port,
            120.0,
            300.0,
            log_cb,
            False,
            cancel_event=self.ft_transfer_cancel_event,
        )
        if child:
            with lk:
                self.ft_sessions[iid] = child
            self._ft_set_conn_status(iid, "Connected")
            return child
        failures.append(f"{tag} reconnect failed: {err}")
        self._ft_set_conn_status(iid, "Error")
        return None

    def _ft_disconnect_all(self) -> None:
        """Close all persistent device shells and reset Connection column."""
        self.ft_connect_cancel_event.set()
        try:
            sc = self._ft_import_sshcommand()
        except Exception:
            sc = None

        def _lo(_m: str) -> None:
            return None

        for iid in list(self.ft_sessions.keys()):
            lk = self._ft_lock_for(iid)
            with lk:
                ch = self.ft_sessions.pop(iid, None)
            if ch is None:
                continue
            try:
                if sc is not None:
                    sc.detach_device_shell(ch, 120.0, _lo)
            except Exception:
                pass
            try:
                ch.close(force=True)
            except Exception:
                pass

        self.ft_sessions.clear()

        for ent in self.ft_inventory:
            if self.ft_tree.exists(ent["iid"]):
                st = "—" if not ent["eligible"] else "Disconnected"
                self._ft_set_conn_status(ent["iid"], st)

    def _ft_iid_for_device(self, sc: Any, name: str, port: int) -> Optional[str]:
        want = (name or "").strip() or "(unnamed)"
        for ent in self.ft_inventory:
            r = ent["raw"]
            got = (r.get("Name") or "").strip() or "(unnamed)"
            if got != want:
                continue
            p = sc.is_valid_sdm_port(r.get("SDM Port") or "")
            if p == port:
                return ent["iid"]
        return None

    def _ft_single_selection_iid(self) -> Optional[str]:
        rows = self._ft_get_selected_raw_rows()
        if len(rows) != 1:
            return None
        r0 = rows[0]
        try:
            sc = self._ft_import_sshcommand()
        except Exception:
            return None
        p0 = sc.is_valid_sdm_port(r0.get("SDM Port") or "")
        n0 = (r0.get("Name") or "").strip() or "(unnamed)"
        for ent in self.ft_inventory:
            if not ent["eligible"]:
                continue
            vals = self.ft_tree.item(ent["iid"])["values"]
            if not vals or vals[0] != "☑":
                continue
            r = ent["raw"]
            p1 = sc.is_valid_sdm_port(r.get("SDM Port") or "")
            n1 = (r.get("Name") or "").strip() or "(unnamed)"
            if n1 == n0 and p0 == p1:
                return ent["iid"]
        return None

    def _ft_connect_clicked(self) -> None:
        if not self._ft_ssh_settings_ok():
            return
        targets: List[Tuple[str, Dict[str, str]]] = []
        for ent in self.ft_inventory:
            if not ent["eligible"]:
                continue
            vals = self.ft_tree.item(ent["iid"])["values"]
            if vals and vals[0] == "☑":
                targets.append((ent["iid"], ent["raw"]))
        if not targets:
            messagebox.showwarning("Connect", "Check at least one AP with a valid SDM port.")
            return
        self.ft_connect_cancel_event.clear()
        threading.Thread(target=self._ft_connect_worker, args=(targets,), daemon=True).start()

    def _ft_connect_worker(self, targets: List[Tuple[str, Dict[str, str]]]) -> None:
        try:
            sc, ssh_cmd = self._ft_build_ssh()
        except Exception as e:
            self.root.after(0, lambda err=str(e): self._ft_log(f"Connect failed: {err}"))
            return

        n_total = len(targets)
        extra_retries = self._ft_parse_rel_int(self.ft_rel_extra_retries_var, 2, 0, 8)
        backoff_base = self._ft_parse_rel_seconds(self.ft_rel_backoff_var, 0.5, 0.05, 10.0)
        pause_ok = self._ft_parse_rel_seconds(self.ft_rel_pause_connect_var, 0.2, 0.0, 5.0)
        want_ping = self.ft_rel_ping_var.get()

        ok_n = 0
        fail_n = 0
        stopped_global = False

        for idx, (iid, raw) in enumerate(targets, start=1):
            if stopped_global:
                break
            if self.ft_connect_cancel_event.is_set():
                self.root.after(0, lambda: self._ft_log("Connect cancelled (Disconnect)."))
                break

            port = sc.is_valid_sdm_port(raw.get("SDM Port") or "")
            if port is None:
                fail_n += 1
                continue

            name_disp = self._ft_display_name(raw)
            self.root.after(
                0,
                lambda i2=idx, nt=n_total, nd=name_disp, prt=port: self._ft_log(
                    f"Connect AP {i2}/{nt}: {nd} port={prt}"
                ),
            )

            lock = self._ft_lock_for(iid)

            def mklog(ii: str) -> Callable[[str], None]:
                return lambda m: self.root.after(0, lambda mm=m, i2=ii: self._ft_log(f"[{i2}] {mm}"))

            lg = mklog(iid)
            got_connected = False
            backoff_used = 0.0
            max_backoff_per_ap = 4.0

            for attempt in range(extra_retries + 1):
                if self.ft_connect_cancel_event.is_set():
                    self.root.after(0, lambda: self._ft_log("Connect cancelled (Disconnect)."))
                    stopped_global = True
                    break

                remaining_cap = max(0.0, max_backoff_per_ap - backoff_used)

                if attempt > 0:
                    mx = extra_retries + 1
                    self.root.after(
                        0,
                        lambda a=attempt, mx=mx, ii=iid: self._ft_log(
                            f"[{ii}] connect retry attempt {a + 1}/{mx}"
                        ),
                    )

                old: Any = None
                try:
                    with lock:
                        old = self.ft_sessions.pop(iid, None)
                        if old is not None:
                            sc.detach_device_shell(old, 120.0, lambda _m: None)
                except Exception:
                    try:
                        if old is not None:
                            old.close(force=True)
                    except Exception:
                        pass

                self.root.after(0, lambda ii=iid: self._ft_set_conn_status(ii, "Connecting…"))

                err = ""
                child: Any = None
                try:
                    with lock:
                        child, err = sc.attach_device_shell(
                            ssh_cmd,
                            port,
                            120.0,
                            300.0,
                            lg,
                            False,
                            cancel_event=self.ft_connect_cancel_event,
                        )
                except Exception as e:
                    err = f"milestone=attach: {e}"

                if err == "cancelled" or (not child and err and "cancelled" in err.lower()):
                    with lock:
                        self.ft_sessions.pop(iid, None)
                    self.root.after(0, lambda ii=iid: self._ft_set_conn_status(ii, "Disconnected"))
                    self.root.after(0, lambda ii=iid: self._ft_log(f"[{ii}] Connect cancelled."))
                    stopped_global = True
                    break

                if child and want_ping:
                    okp, erp = sc.ping_open_device_shell(
                        child, lg, 12.0, self.ft_connect_cancel_event
                    )
                    if not okp:
                        self._ft_force_close_child(sc, child)
                        with lock:
                            self.ft_sessions.pop(iid, None)
                        child = None
                        err = erp or "ping failed"

                if child:
                    with lock:
                        self.ft_sessions[iid] = child
                    self.root.after(0, lambda ii=iid: self._ft_set_conn_status(ii, "Connected"))
                    ok_n += 1
                    got_connected = True
                    if pause_ok > 0:
                        time.sleep(pause_ok)
                    break

                err_txt = err or "unknown error"
                may_retry = (
                    attempt < extra_retries
                    and self._ft_is_transient_connect_error(err_txt)
                    and not self.ft_connect_cancel_event.is_set()
                )

                if may_retry and remaining_cap > 0:
                    self.root.after(
                        0,
                        lambda er=err_txt, ii=iid: self._ft_log(f"[{ii}] {er} (will retry)"),
                    )
                    sleep_t = min(backoff_base * (2**attempt), remaining_cap, 2.0)
                    if sleep_t > 0:
                        time.sleep(sleep_t)
                        backoff_used += sleep_t
                    with lock:
                        self.ft_sessions.pop(iid, None)
                    continue

                self.root.after(0, lambda er=err_txt, ii=iid: self._ft_log(f"[{ii}] {er}"))
                self.root.after(0, lambda ii=iid: self._ft_set_conn_status(ii, "Error"))
                fail_n += 1
                with lock:
                    self.ft_sessions.pop(iid, None)
                break

            if stopped_global:
                break

        self.root.after(
            0,
            lambda on=ok_n, fn=fail_n, nt=n_total: self._ft_log(
                f"Connect finished: succeeded={on}, failed={fn}, queued={nt}"
            ),
        )

    def _ft_log(self, msg: str) -> None:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.ft_log_text.insert(tk.END, f"[{ts}] {msg}\n")
        self.ft_log_text.see(tk.END)

    def _ft_clear_log(self) -> None:
        self.ft_log_text.delete(1.0, tk.END)

    def _ft_browse_rsa(self) -> None:
        p = filedialog.askopenfilename(title="SSH private key", filetypes=[("All files", "*.*")])
        if p:
            self.ft_rsa_var.set(p)

    def _ft_browse_csv(self) -> None:
        p = filedialog.askopenfilename(title="Inventory CSV", filetypes=[("CSV", "*.csv"), ("All", "*.*")])
        if p:
            self._ft_load_csv(Path(p))

    def _ft_load_csv(self, path: Path) -> None:
        if hasattr(self, "_ft_invalidate_insight_snapshot"):
            self._ft_invalidate_insight_snapshot()
        if hasattr(self, "ft_manual_rows"):
            self.ft_manual_rows.clear()
        try:
            with path.open(newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    messagebox.showerror("CSV", "CSV has no header row.")
                    return
                fn = list(reader.fieldnames)
                if "SDM Port" not in fn:
                    messagebox.showerror("CSV", "CSV must include column 'SDM Port'.")
                    return
                if "Name" not in fn:
                    fn = ["Name"] + fn
                rows = list(reader)
        except OSError as e:
            messagebox.showerror("CSV", str(e))
            return

        self._ft_disconnect_all()

        self.ft_csv_path = path.resolve()
        self.ft_csv_fieldnames = fn
        self.ft_inventory = []
        sc = None
        try:
            sc = self._ft_import_sshcommand()
        except Exception as e:
            messagebox.showerror("Import", f"Could not load sshcommand: {e}")
            return

        for i, raw in enumerate(rows):
            raw_copy = dict(raw)
            if "Name" not in raw_copy:
                raw_copy["Name"] = ""
            port_ok = sc.is_valid_sdm_port(raw_copy.get("SDM Port") or "") is not None
            eligible = port_ok
            self.ft_inventory.append(
                {"iid": str(i), "raw": raw_copy, "eligible": eligible, "manual": False}
            )

        for it in self.ft_tree.get_children():
            self.ft_tree.delete(it)
        for entry in self.ft_inventory:
            r = entry["raw"]
            dn = self._ft_display_name(r)
            self.ft_tree.insert(
                "",
                tk.END,
                iid=entry["iid"],
                values=(
                    "☐",
                    dn,
                    r.get("IP", "") or "",
                    r.get("Model", "") or "",
                    r.get("SDM Status", "") or "",
                    r.get("SDM Port", "") or "",
                    "—" if not entry["eligible"] else "Disconnected",
                ),
            )

        n_elig = sum(1 for e in self.ft_inventory if e["eligible"])
        self.ft_csv_label_var.set(
            f"Loaded: {path.name} — rows={len(self.ft_inventory)}, selectable (valid SDM port)={n_elig}"
        )
        self._ft_update_summary()
        self._ft_log(f"Loaded CSV {path} ({len(self.ft_inventory)} rows, {n_elig} selectable).")
        self._ft_sync_run_button_state()

    def _ft_add_manual_port_clicked(self) -> None:
        if getattr(self, "ft_csv_path", None):
            messagebox.showwarning("Add port", "Clear CSV first to add manual AP rows.")
            return
        try:
            sc = self._ft_import_sshcommand()
        except Exception as exc:
            messagebox.showerror("Add port", str(exc))
            return

        win = tk.Toplevel(self.root)
        win.title("Add SDM port")
        win.transient(self.root)
        win.grab_set()

        v_port = tk.StringVar()
        v_name = tk.StringVar()
        v_ip = tk.StringVar()
        v_model = tk.StringVar()
        v_status = tk.StringVar()

        grid = ttk.Frame(win, padding=12)
        grid.pack(fill=tk.BOTH, expand=True)
        r = 0
        ttk.Label(grid, text="SDM Port *").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(grid, textvariable=v_port, width=18).grid(row=r, column=1, sticky="w", pady=2)
        r += 1
        ttk.Label(grid, text="Name").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(grid, textvariable=v_name, width=40).grid(row=r, column=1, sticky="ew", pady=2)
        r += 1
        ttk.Label(grid, text="IP").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(grid, textvariable=v_ip, width=40).grid(row=r, column=1, sticky="ew", pady=2)
        r += 1
        ttk.Label(grid, text="Model").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(grid, textvariable=v_model, width=40).grid(row=r, column=1, sticky="ew", pady=2)
        r += 1
        ttk.Label(grid, text="SDM Status").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(grid, textvariable=v_status, width=40).grid(row=r, column=1, sticky="ew", pady=2)
        grid.columnconfigure(1, weight=1)

        def on_ok() -> None:
            port_raw = v_port.get().strip()
            p = sc.is_valid_sdm_port(port_raw)
            if p is None:
                messagebox.showerror("Add port", "Enter a valid SDM Port (1–65535).", parent=win)
                return
            raw = {
                "Name": v_name.get().strip(),
                "SDM Port": str(p),
                "SDM Status": v_status.get().strip() or "Manual",
                "IP": v_ip.get().strip(),
                "Model": v_model.get().strip(),
            }
            iid = str(uuid.uuid4())
            self.ft_manual_rows.append({"iid": iid, "raw": raw})
            if not getattr(self, "ft_csv_path", None):
                self._ft_insert_manual_row_live(sc, iid, raw)
            win.destroy()

        def on_cancel() -> None:
            win.destroy()

        btn = ttk.Frame(win, padding=(12, 0, 12, 12))
        btn.pack(fill=tk.X)
        ttk.Button(btn, text="OK", command=on_ok).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn, text="Cancel", command=on_cancel).pack(side=tk.LEFT)

    def _ft_remove_manual_port_clicked(self) -> None:
        sel = self.ft_tree.selection()
        if not sel:
            messagebox.showwarning("Remove", "Select a row to remove.")
            return
        iid = sel[0]
        ent = next((e for e in self.ft_inventory if e["iid"] == iid), None)
        if not ent or not ent.get("manual"):
            messagebox.showwarning("Remove", "Only manually added rows can be removed.")
            return
        try:
            sc = self._ft_import_sshcommand()
        except Exception:
            sc = None
        ch = None
        lk = self._ft_lock_for(iid)
        with lk:
            ch = self.ft_sessions.pop(iid, None)
        if ch is not None and sc is not None:
            try:
                sc.detach_device_shell(ch, 120.0, lambda _m: None)
            except Exception:
                try:
                    ch.close(force=True)
                except Exception:
                    pass
        elif ch is not None:
            try:
                ch.close(force=True)
            except Exception:
                pass
        self.ft_manual_rows = [m for m in self.ft_manual_rows if m.get("iid") != iid]
        self.ft_inventory = [e for e in self.ft_inventory if e["iid"] != iid]
        self.ft_tree.delete(iid)
        self._ft_update_inventory_status_message()
        self._ft_on_tree_select()

    def _ft_toggle_row(self, event: tk.Event) -> None:
        row_id = self.ft_tree.identify_row(event.y)
        if not row_id:
            return
        entry = next((e for e in self.ft_inventory if e["iid"] == row_id), None)
        if entry is None:
            return
        if not entry["eligible"]:
            messagebox.showwarning("Selection", "Only rows with a valid SDM Port (1–65535) can be selected.")
            return
        vals = list(self.ft_tree.item(row_id)["values"])
        while len(vals) < 7:
            vals.append("Disconnected")
        vals[0] = "☑" if vals[0] == "☐" else "☐"
        self.ft_tree.item(row_id, values=vals)
        self._ft_on_tree_select()

    def _ft_check_all(self) -> None:
        for entry in self.ft_inventory:
            if not entry["eligible"]:
                continue
            iid = entry["iid"]
            vals = list(self.ft_tree.item(iid)["values"])
            while len(vals) < 7:
                vals.append("Disconnected")
            vals[0] = "☑"
            self.ft_tree.item(iid, values=vals)
        self._ft_on_tree_select()

    def _ft_check_none(self) -> None:
        for entry in self.ft_inventory:
            iid = entry["iid"]
            vals = list(self.ft_tree.item(iid)["values"])
            while len(vals) < 7:
                vals.append("Disconnected")
            vals[0] = "☐"
            self.ft_tree.item(iid, values=vals)
        self._ft_on_tree_select()

    def _ft_count_selected_eligible(self) -> int:
        n = 0
        for entry in self.ft_inventory:
            if not entry["eligible"]:
                continue
            vals = self.ft_tree.item(entry["iid"])["values"]
            if vals and vals[0] == "☑":
                n += 1
        return n

    def _ft_get_selected_raw_rows(self) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        for entry in self.ft_inventory:
            if not entry["eligible"]:
                continue
            vals = self.ft_tree.item(entry["iid"])["values"]
            if vals and vals[0] == "☑":
                out.append(entry["raw"])
        return out

    def _ft_single_selection_port(self) -> Optional[int]:
        rows = self._ft_get_selected_raw_rows()
        if len(rows) != 1:
            return None
        sc = self._ft_import_sshcommand()
        return sc.is_valid_sdm_port(rows[0].get("SDM Port") or "")

    def _ft_on_tree_select(self) -> None:
        self.ft_sel_count_var.set(f"Selected APs (valid port): {self._ft_count_selected_eligible()}")
        self._ft_update_selection_layout()
        self._ft_update_summary()
        self._ft_sync_run_button_state()

    def _ft_update_selection_layout(self) -> None:
        if self._ft_count_selected_eligible() == 1:
            self.ft_batch_frame.pack_forget()
            self.ft_explorer_frame.pack(fill=tk.BOTH, expand=True)
            self.ft_local_cwd_var.set(str(self.ft_local_cwd))
            self._ft_refresh_local_list()
        else:
            self.ft_explorer_frame.pack_forget()
            self.ft_batch_frame.pack(fill=tk.BOTH, expand=True)

    def _ft_on_mode_change(self) -> None:
        mode = self.ft_mode_var.get()
        if mode == "upload":
            self.ft_batch_row1.pack(fill=tk.X, pady=4)
            self.ft_batch_path_label.config(text="Destination directory on APs (must exist):")
            self.ft_batch_row2.pack(fill=tk.X, pady=4)
            self.ft_batch_local_label.config(text="Local files to upload:")
            self.ft_batch_files_list.pack(fill=tk.BOTH, expand=True, pady=4)
            self.ft_batch_dl_row.pack_forget()
        else:
            self.ft_batch_row1.pack_forget()
            self.ft_batch_row2.pack_forget()
            self.ft_batch_files_list.pack_forget()
            self.ft_batch_dl_row.pack(fill=tk.BOTH, expand=True, pady=4)
        self._ft_update_summary()

    def _ft_browse_batch_upload_files(self) -> None:
        paths = filedialog.askopenfilenames(title="Files to upload")
        if not paths:
            return
        for p in paths:
            lp = Path(p).resolve()
            if lp.is_file() and lp not in self.ft_batch_upload_paths:
                self.ft_batch_upload_paths.append(lp)
        self.ft_batch_files_list.delete(0, tk.END)
        for p in self.ft_batch_upload_paths:
            self.ft_batch_files_list.insert(tk.END, str(p))
        self._ft_update_summary()

    def _ft_clear_batch_files(self) -> None:
        self.ft_batch_upload_paths.clear()
        self.ft_batch_files_list.delete(0, tk.END)
        self._ft_update_summary()

    def _ft_browse_batch_local_dir(self) -> None:
        d = filedialog.askdirectory(title="Download folder")
        if d:
            self.ft_batch_local_dir_var.set(d)
            self._ft_update_summary()

    def _ft_clear_form(self) -> None:
        self.ft_url_var.set(FT_DEFAULT_JUMP_SSH_URL)
        self.ft_rsa_var.set("")
        self.ft_ssh_port_var.set("443")
        self.ft_batch_ap_path_var.set("")
        self.ft_batch_remote_paths_text.delete("1.0", tk.END)
        self.ft_batch_local_dir_var.set("")
        self.ft_upload_binary_var.set(False)
        if hasattr(self, "ft_download_timeout_var"):
            self.ft_download_timeout_var.set("900")
        self._ft_clear_batch_files()
        self._ft_disconnect_all()
        self._ft_update_summary()

    def _ft_update_summary(self) -> None:
        mode = self.ft_mode_var.get()
        self.ft_run_btn.config(text="Upload" if mode == "upload" else "Download")
        self._ft_sync_run_button_state()

    def _ft_sync_run_button_state(self) -> None:
        if not hasattr(self, "ft_run_btn"):
            return
        one = self._ft_count_selected_eligible() == 1
        st = tk.DISABLED if self.ft_busy or one else tk.NORMAL
        self.ft_run_btn.config(state=st)

    def _ft_set_busy(self, busy: bool) -> None:
        self.ft_busy = busy
        self.ft_remote_refresh_btn.config(state=tk.DISABLED if busy else tk.NORMAL)
        if hasattr(self, "ft_stop_btn"):
            self.ft_stop_btn.config(state=tk.NORMAL if busy else tk.DISABLED)
        if not busy:
            self._ft_reset_download_progress()
        self._ft_sync_run_button_state()

    def _ft_ssh_settings_ok(self) -> bool:
        url = self.ft_url_var.get().strip()
        rsa = self.ft_rsa_var.get().strip()
        if not url or "@" not in url:
            messagebox.showerror("SSH", "Enter jump URL as user@host.")
            return False
        if not rsa or not Path(rsa).expanduser().is_file():
            messagebox.showerror("SSH", "Choose a valid SSH private key file.")
            return False
        try:
            int(self.ft_ssh_port_var.get().strip() or "443")
        except ValueError:
            messagebox.showerror("SSH", "Jump SSH port must be an integer.")
            return False
        return True

    def _ft_write_temp_csv(self, rows: List[Dict[str, str]]) -> Path:
        fd, name = tempfile.mkstemp(suffix=".csv", prefix="sdm_ft_")
        os.close(fd)
        p = Path(name)
        with p.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=self.ft_csv_fieldnames, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in self.ft_csv_fieldnames})
        return p

    def _ft_sanitize_dir_name(self, name: str) -> str:
        s = re.sub(r"[^\w\-.]+", "_", (name or "ap").strip())[:120]
        return s or "ap"

    def _ft_get_batch_remote_paths(self) -> List[str]:
        """Non-empty lines from the batch download remote-paths text box."""
        raw = self.ft_batch_remote_paths_text.get("1.0", tk.END)
        return [ln.strip() for ln in raw.splitlines() if ln.strip()]

    def _ft_run_transfer(self) -> None:
        if self.ft_busy:
            return
        if not self._ft_ssh_settings_ok():
            return
        rows = self._ft_get_selected_raw_rows()
        if not rows:
            messagebox.showwarning("Transfer", "Select at least one AP with a valid SDM port.")
            return
        if not self.ft_csv_fieldnames:
            messagebox.showwarning("Transfer", "Load devices from Device Management or browse a CSV export.")
            return

        mode = self.ft_mode_var.get()
        if len(rows) > 1:
            if mode == "upload":
                dest = self.ft_batch_ap_path_var.get().strip()
                if not dest:
                    messagebox.showerror("Upload", "Enter destination directory on APs.")
                    return
                if not self.ft_batch_upload_paths:
                    messagebox.showerror("Upload", "Choose one or more local files.")
                    return
            else:
                rpaths = self._ft_get_batch_remote_paths()
                lf = self.ft_batch_local_dir_var.get().strip()
                if not rpaths or not lf:
                    messagebox.showerror(
                        "Download",
                        "Enter at least one remote file path (one per line) and a local folder.",
                    )
                    return
                if not Path(lf).expanduser().is_dir():
                    messagebox.showerror("Download", "Local folder must exist.")
                    return
                try:
                    self._ft_parse_download_timeout_sec()
                except ValueError:
                    messagebox.showerror(
                        "Download",
                        "Download timeout must be a number between 30 and 86400 seconds.",
                    )
                    return
        threading.Thread(target=self._ft_run_transfer_thread, daemon=True).start()

    def _ft_run_transfer_thread(self) -> None:
        self.ft_transfer_cancel_event.clear()
        self.root.after(0, lambda: self._ft_set_busy(True))
        try:
            rows = self._ft_get_selected_raw_rows()
            mode = self.ft_mode_var.get()
            if len(rows) > 1:
                tmp = self._ft_write_temp_csv(rows)
                try:
                    if mode == "upload":
                        self._ft_exec_batch_upload(tmp)
                    else:
                        self._ft_exec_batch_download(tmp)
                finally:
                    try:
                        tmp.unlink()
                    except OSError:
                        pass
            elif len(rows) == 1:
                pass
        except Exception as e:
            self.root.after(0, lambda: self._ft_log(f"ERROR: {e}"))
            self.root.after(0, lambda err=str(e): messagebox.showerror("Transfer", err))
        finally:
            self.root.after(0, lambda: self._ft_set_busy(False))

    def _ft_build_ssh(self) -> Tuple[Any, List[str]]:
        sc = self._ft_import_sshcommand()
        user, host = sc.parse_user_at_host(self.ft_url_var.get().strip())
        port = int(self.ft_ssh_port_var.get().strip() or "443")
        key = Path(self.ft_rsa_var.get().strip()).expanduser()
        ssh_cmd = sc.build_ssh_cmd(
            user,
            host,
            port,
            key,
            strict_host_key_checking=True,
            accept_new_host_key=True,
        )
        return sc, ssh_cmd

    def _ft_exec_batch_upload(self, csv_path: Path) -> None:
        sc, ssh_cmd = self._ft_build_ssh()
        batch_pause = self._ft_parse_rel_seconds(self.ft_rel_pause_batch_var, 0.15, 0.0, 5.0)
        dest_base = self.ft_batch_ap_path_var.get().strip().rstrip("/")
        uploads: List[Any] = []
        want_x = self.ft_upload_binary_var.get()
        for lp in self.ft_batch_upload_paths:
            spec = sc.parse_upload_arg(f"{lp}:{posixpath.join(dest_base, lp.name)}")
            if want_x:
                spec = replace(spec, chmod_mode="+x")
            uploads.append(spec)
        devices = list(
            sc.iter_target_devices(
                csv_path,
                port_column="SDM Port",
                name_column="Name",
                require_sdm_enabled=False,
            )
        )
        if not devices:
            self.root.after(0, lambda: self._ft_log("No devices in temp CSV (need a valid SDM Port per row)."))
            return

        cmd_t = 300.0
        failures: List[str] = []
        cancelled = False
        attempted_any = False
        all_ok = True

        for dev in devices:
            try:
                if self.ft_transfer_cancel_event.is_set():
                    cancelled = True
                    break
                tag = f"[{dev.name} port={dev.sdm_port}]"
                iid = self._ft_iid_for_device(sc, dev.name, dev.sdm_port)
                if not iid:
                    failures.append(f"{tag} skipped (no table row).")
                    all_ok = False
                    continue

                def make_log(t: str) -> Callable[[str], None]:
                    return lambda m: self.root.after(0, lambda mm=m, tt=t: self._ft_log(f"{tt} {mm}"))

                log_cb = make_log(tag)
                ch = self._ft_ensure_batch_channel(sc, ssh_cmd, iid, tag, failures, log_cb)
                if not ch:
                    all_ok = False
                    continue

                for spec in uploads:
                    if self.ft_transfer_cancel_event.is_set():
                        cancelled = True
                        break
                    if not self._ft_shell_alive(ch):
                        ch = self._ft_ensure_batch_channel(sc, ssh_cmd, iid, tag, failures, log_cb)
                        if not ch:
                            all_ok = False
                            break
                    attempted_any = True
                    self._ft_begin_transfer_ops(iid, ch)
                    try:
                        ok, det = sc.run_ops_on_open_shell(
                            ch,
                            [spec],
                            [],
                            [],
                            cmd_t,
                            log_cb,
                            log_cb,
                            cancel_event=self.ft_transfer_cancel_event,
                        )
                    finally:
                        self._ft_end_transfer_ops()
                    if ok:
                        self.root.after(
                            0, lambda t=tag, n=spec.local_path.name: self._ft_log(f"{t} upload ok: {n}")
                        )
                    else:
                        all_ok = False
                        if det == "cancelled":
                            cancelled = True
                            break
                        failures.append(f"{tag} upload {spec.local_path.name} -> {spec.device_path}: {det}")
                    if getattr(ch, "closed", False):
                        lk2 = self._ft_lock_for(iid)
                        with lk2:
                            if self.ft_sessions.get(iid) is ch:
                                self.ft_sessions.pop(iid, None)
                        self._ft_set_conn_status(iid, "Disconnected")
                        failures.append(f"{tag} session closed; remaining files skipped for this AP.")
                        break
                if cancelled:
                    break
            finally:
                if batch_pause > 0 and not self.ft_transfer_cancel_event.is_set():
                    time.sleep(batch_pause)

        def _finish() -> None:
            if cancelled and not failures:
                self._ft_log("Upload batch cancelled.")
            elif not cancelled and attempted_any and all_ok and not failures:
                messagebox.showinfo("Upload", "All files uploaded successfully for every AP.")
            elif failures:
                self._ft_show_failures_dialog("Upload failures", failures)

        self.root.after(0, _finish)

    def _ft_exec_batch_download(self, csv_path: Path) -> None:
        sc, ssh_cmd = self._ft_build_ssh()
        batch_pause = self._ft_parse_rel_seconds(self.ft_rel_pause_batch_var, 0.15, 0.0, 5.0)
        remote_paths = self._ft_get_batch_remote_paths()
        local_root = Path(self.ft_batch_local_dir_var.get().strip()).expanduser()
        devices = list(
            sc.iter_target_devices(
                csv_path,
                port_column="SDM Port",
                name_column="Name",
                require_sdm_enabled=False,
            )
        )
        if not devices:
            self.root.after(0, lambda: self._ft_log("No devices in temp CSV (need a valid SDM Port per row)."))
            return

        try:
            dl_sec = self._ft_parse_download_timeout_sec()
        except ValueError:
            dl_sec = 900.0

        cmd_t = 300.0
        failures: List[str] = []
        cancelled = False
        attempted_any = False
        all_ok = True
        total_ops = max(len(devices) * len(remote_paths), 1)
        cur_done = 0

        for dev in devices:
            try:
                if self.ft_transfer_cancel_event.is_set():
                    cancelled = True
                    break
                tag = f"[{dev.name} port={dev.sdm_port}]"
                iid = self._ft_iid_for_device(sc, dev.name, dev.sdm_port)
                if not iid:
                    failures.append(f"{tag} skipped (no table row).")
                    all_ok = False
                    continue
                sub = local_root / self._ft_sanitize_dir_name(dev.name)
                sub.mkdir(parents=True, exist_ok=True)

                def make_log(t: str) -> Callable[[str], None]:
                    return lambda m: self.root.after(0, lambda mm=m, tt=t: self._ft_log(f"{tt} {mm}"))

                log_cb = make_log(tag)
                ch = self._ft_ensure_batch_channel(sc, ssh_cmd, iid, tag, failures, log_cb)
                if not ch:
                    all_ok = False
                    continue

                for remote_file in remote_paths:
                    if self.ft_transfer_cancel_event.is_set():
                        cancelled = True
                        break
                    if not self._ft_shell_alive(ch):
                        ch = self._ft_ensure_batch_channel(sc, ssh_cmd, iid, tag, failures, log_cb)
                        if not ch:
                            all_ok = False
                            break
                    base_name = posixpath.basename(remote_file) or "download"
                    local_path = sub / base_name
                    one_dl = [sc.parse_download_arg(f"{remote_file}:{local_path}")]
                    cur_done += 1
                    self._ft_set_download_progress(
                        cur_done - 1,
                        total_ops,
                        f"{tag} {remote_file} ({cur_done}/{total_ops})",
                    )
                    attempted_any = True
                    self._ft_begin_transfer_ops(iid, ch)
                    try:
                        ok, det = sc.run_ops_on_open_shell(
                            ch,
                            [],
                            [],
                            one_dl,
                            cmd_t,
                            log_cb,
                            log_cb,
                            download_timeout=dl_sec,
                            cancel_event=self.ft_transfer_cancel_event,
                        )
                    finally:
                        self._ft_end_transfer_ops()
                    self._ft_set_download_progress(
                        cur_done,
                        total_ops,
                        f"{tag} done {cur_done}/{total_ops}",
                    )
                    if ok:
                        self.root.after(
                            0,
                            lambda t=tag, rp=remote_file, sd=sub: self._ft_log(f"{t} saved {rp} -> {sd}"),
                        )
                    else:
                        all_ok = False
                        if det == "cancelled":
                            cancelled = True
                            break
                        failures.append(f"{tag} download {remote_file}: {det}")
                    if getattr(ch, "closed", False):
                        lk2 = self._ft_lock_for(iid)
                        with lk2:
                            if self.ft_sessions.get(iid) is ch:
                                self.ft_sessions.pop(iid, None)
                        self._ft_set_conn_status(iid, "Disconnected")
                        failures.append(f"{tag} session closed; remaining downloads skipped for this AP.")
                        break
                if cancelled:
                    break
            finally:
                if batch_pause > 0 and not self.ft_transfer_cancel_event.is_set():
                    time.sleep(batch_pause)

        def _finish() -> None:
            if cancelled and not failures:
                self._ft_log("Download batch cancelled.")
            elif not cancelled and attempted_any and all_ok and not failures:
                messagebox.showinfo("Download", "All files downloaded successfully for every AP.")
            elif failures:
                self._ft_show_failures_dialog("Download failures", failures)

        self.root.after(0, _finish)

    def _ft_local_go(self) -> None:
        p = Path(self.ft_local_cwd_var.get().strip()).expanduser()
        if p.is_dir():
            self.ft_local_cwd = p.resolve()
            self.ft_local_cwd_var.set(str(self.ft_local_cwd))
            self._ft_refresh_local_list()
        else:
            messagebox.showerror("Local", "Not a directory.")

    def _ft_refresh_local_list(self) -> None:
        self.ft_local_list.delete(0, tk.END)
        try:
            names = sorted(self.ft_local_cwd.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except OSError as e:
            self.ft_local_list.insert(tk.END, f"(error: {e})")
            return
        cur = self.ft_local_cwd.resolve()
        if cur != cur.parent:
            self.ft_local_list.insert(tk.END, "..")
        for ch in names:
            mark = "/" if ch.is_dir() else ""
            self.ft_local_list.insert(tk.END, f"{ch.name}{mark}")

    def _ft_local_double_click(self, event: tk.Event) -> None:
        sel = self.ft_local_list.curselection()
        if not sel:
            return
        name = self.ft_local_list.get(sel[0]).rstrip("/")
        if name == "..":
            self.ft_local_cwd = self.ft_local_cwd.parent.resolve()
            self.ft_local_cwd_var.set(str(self.ft_local_cwd))
            self._ft_refresh_local_list()
            return
        p = (self.ft_local_cwd / name).resolve()
        if p.is_dir():
            self.ft_local_cwd = p
            self.ft_local_cwd_var.set(str(self.ft_local_cwd))
            self._ft_refresh_local_list()

    def _ft_remote_go(self) -> None:
        self._ft_refresh_remote_list()

    def _ft_refresh_remote_list(self) -> None:
        if self._ft_count_selected_eligible() != 1:
            return
        threading.Thread(target=self._ft_remote_list_thread, daemon=True).start()

    def _ft_remote_list_thread(self) -> None:
        self.root.after(0, lambda: self._ft_set_busy(True))
        try:
            iid = self._ft_single_selection_iid()
            if not iid:
                return
            sc, _ssh_cmd = self._ft_build_ssh()
            rp = self.ft_remote_cwd_var.get().strip() or "/"
            cmd = f"ls -1A {shlex.quote(rp)}"
            tag = "[remote]"

            def lg(m: str) -> None:
                self.root.after(0, lambda mm=m, tt=tag: self._ft_log(f"{tt} {mm}"))

            lk = self._ft_lock_for(iid)
            with lk:
                ch = self.ft_sessions.get(iid)
            if not ch:
                self.root.after(0, lambda: self._ft_log("Remote list: Connect first."))
                return
            outputs: List[str] = []
            ok, err2 = sc.run_ops_on_open_shell(
                ch,
                [],
                [cmd],
                [],
                120.0,
                lg,
                lg,
                command_outputs=outputs,
            )
            if not ok:
                self.root.after(0, lambda er=err2: self._ft_log(f"Remote list failed: {er}"))
                return
            text = outputs[0] if outputs else ""
            lines = [sc._strip_ansi(ln) for ln in text.splitlines() if ln.strip()]
            if ".." not in lines and rp not in ("/", ""):
                lines = [".."] + lines

            def apply() -> None:
                self.ft_remote_list.delete(0, tk.END)
                for ln in lines:
                    self.ft_remote_list.insert(tk.END, ln)

            self.root.after(0, apply)
        finally:
            self.root.after(0, lambda: self._ft_set_busy(False))

    def _ft_remote_double_click(self, event: tk.Event) -> None:
        if self._ft_count_selected_eligible() != 1:
            return
        sel = self.ft_remote_list.curselection()
        if not sel:
            return
        name = self.ft_remote_list.get(sel[0]).strip()
        base = self.ft_remote_cwd_var.get().strip() or "/"
        if name == "..":
            if base == "/":
                parent = "/"
            else:
                parent = posixpath.normpath(posixpath.join(base, ".."))
            self.ft_remote_cwd_var.set(parent or "/")
            self._ft_refresh_remote_list()
            return
        full = posixpath.normpath(posixpath.join(base, name))
        threading.Thread(target=lambda: self._ft_remote_nav_thread(full), daemon=True).start()

    def _ft_remote_nav_thread(self, full: str) -> None:
        self.root.after(0, lambda: self._ft_set_busy(True))
        try:
            iid = self._ft_single_selection_iid()
            if not iid:
                return
            sc, _ssh_cmd = self._ft_build_ssh()
            cmd = f"if [ -d {shlex.quote(full)} ]; then echo __D__; elif [ -f {shlex.quote(full)} ] || [ -L {shlex.quote(full)} ]; then echo __F__; else echo __E__; fi"

            def lg(m: str) -> None:
                pass

            lk = self._ft_lock_for(iid)
            with lk:
                ch = self.ft_sessions.get(iid)
            if not ch:
                self.root.after(0, lambda: self._ft_log("Remote nav: Connect first."))
                return
            outs: List[str] = []
            ok, res = sc.run_ops_on_open_shell(
                ch,
                [],
                [cmd],
                [],
                60.0,
                lg,
                lg,
                command_outputs=outs,
            )
            if not ok:
                self.root.after(0, lambda rr=res: self._ft_log(f"Remote check failed: {rr}"))
                return
            if not outs:
                self.root.after(0, lambda: self._ft_log("Remote check: empty output."))
                return
            out = (outs[0] or "").strip()
            if "__D__" in out:
                self.root.after(0, lambda ff=full: self.ft_remote_cwd_var.set(ff))
                self.root.after(0, self._ft_refresh_remote_list)
            elif "__F__" in out:
                self.root.after(0, lambda ff=full: self._ft_log(f"(file) {ff}"))
            else:
                self.root.after(0, lambda ff=full: self._ft_log(f"Not found: {ff}"))
        finally:
            self.root.after(0, lambda: self._ft_set_busy(False))

    def _ft_explorer_upload(self) -> None:
        if self._ft_count_selected_eligible() != 1:
            messagebox.showwarning("Upload", "Select exactly one AP with a valid SDM port.")
            return
        sels = self.ft_local_list.curselection()
        if not sels:
            messagebox.showwarning("Upload", "Select local file(s) in the left list.")
            return
        paths: List[Path] = []
        for i in sels:
            label = self.ft_local_list.get(i).rstrip("/")
            if label.endswith("/") or label == "..":
                messagebox.showwarning("Upload", "Select files only (not directories).")
                return
            p = self.ft_local_cwd / label
            if not p.is_file():
                messagebox.showwarning("Upload", f"Not a file: {p}")
                return
            paths.append(p.resolve())
        threading.Thread(target=lambda: self._ft_explorer_upload_thread(paths), daemon=True).start()

    def _ft_explorer_upload_thread(self, paths: List[Path]) -> None:
        self.ft_transfer_cancel_event.clear()
        self.root.after(0, lambda: self._ft_set_busy(True))
        try:
            rows = self._ft_get_selected_raw_rows()
            if len(rows) != 1:
                return
            iid = self._ft_single_selection_iid()
            if not iid:
                return
            sc, _ssh_cmd = self._ft_build_ssh()
            dest_base = self.ft_remote_cwd_var.get().strip().rstrip("/") or "/"
            want_x = self.ft_upload_binary_var.get()
            tag = f"[{rows[0].get('Name', '')}]"

            def lg(m: str) -> None:
                self.root.after(0, lambda mm=m, tt=tag: self._ft_log(f"{tt} {mm}"))

            lk = self._ft_lock_for(iid)
            with lk:
                ch = self.ft_sessions.get(iid)
            if not ch:
                self.root.after(0, lambda: self._ft_log("Upload: Connect first."))
                return

            failures: List[str] = []
            cancelled = False
            all_ok = True
            for lp in paths:
                if self.ft_transfer_cancel_event.is_set():
                    cancelled = True
                    break
                spec = sc.parse_upload_arg(f"{lp}:{posixpath.join(dest_base, lp.name)}")
                if want_x:
                    spec = replace(spec, chmod_mode="+x")
                self._ft_begin_transfer_ops(iid, ch)
                try:
                    ok, det = sc.run_ops_on_open_shell(
                        ch,
                        [spec],
                        [],
                        [],
                        300.0,
                        lg,
                        lg,
                        cancel_event=self.ft_transfer_cancel_event,
                    )
                finally:
                    self._ft_end_transfer_ops()
                if not ok:
                    all_ok = False
                    if det == "cancelled":
                        cancelled = True
                        break
                    failures.append(f"{tag} upload {spec.local_path.name} -> {spec.device_path}: {det}")
                if getattr(ch, "closed", False):
                    lk2 = self._ft_lock_for(iid)
                    with lk2:
                        if self.ft_sessions.get(iid) is ch:
                            self.ft_sessions.pop(iid, None)
                    self._ft_set_conn_status(iid, "Disconnected")
                    failures.append(f"{tag} session closed; remaining uploads skipped.")
                    break

            def _done() -> None:
                self._ft_log(f"{tag} {'OK' if (all_ok and not failures and not cancelled) else 'finished with issues'}")
                if not cancelled and paths and all_ok and not failures:
                    messagebox.showinfo("Upload", "All selected files uploaded successfully.")
                    self._ft_refresh_remote_list()
                elif failures:
                    self._ft_show_failures_dialog("Upload failures", failures)

            self.root.after(0, _done)
        finally:
            self.root.after(0, lambda: self._ft_set_busy(False))

    def _ft_explorer_download(self) -> None:
        if self._ft_count_selected_eligible() != 1:
            messagebox.showwarning("Download", "Select exactly one AP with a valid SDM port.")
            return
        sels = self.ft_remote_list.curselection()
        if not sels:
            messagebox.showwarning("Download", "Select remote file(s) in the right list.")
            return
        names = []
        for i in sels:
            n = self.ft_remote_list.get(i).strip()
            if n == ".." or n.endswith("/"):
                messagebox.showwarning("Download", "Select files only.")
                return
            names.append(n)
        try:
            self._ft_parse_download_timeout_sec()
        except ValueError:
            messagebox.showerror(
                "Download",
                "Download timeout must be a number between 30 and 86400 seconds.",
            )
            return
        threading.Thread(target=lambda: self._ft_explorer_download_thread(names), daemon=True).start()

    def _ft_explorer_download_thread(self, names: List[str]) -> None:
        self.ft_transfer_cancel_event.clear()
        self.root.after(0, lambda: self._ft_set_busy(True))
        try:
            try:
                dl_sec = self._ft_parse_download_timeout_sec()
            except ValueError:
                dl_sec = 900.0
                self.root.after(0, lambda: self._ft_log("Invalid download timeout; using 900s."))
            rows = self._ft_get_selected_raw_rows()
            if len(rows) != 1:
                return
            iid = self._ft_single_selection_iid()
            if not iid:
                return
            sc, _ssh_cmd = self._ft_build_ssh()
            base = self.ft_remote_cwd_var.get().strip().rstrip("/") or "/"
            tag = f"[{rows[0].get('Name', '')}]"

            def lg(m: str) -> None:
                self.root.after(0, lambda mm=m, tt=tag: self._ft_log(f"{tt} {mm}"))

            lk = self._ft_lock_for(iid)
            with lk:
                ch = self.ft_sessions.get(iid)
            if not ch:
                self.root.after(0, lambda: self._ft_log("Download: Connect first."))
                return

            failures: List[str] = []
            cancelled = False
            all_ok = True
            total = max(len(names), 1)
            cur = 0
            for n in names:
                if self.ft_transfer_cancel_event.is_set():
                    cancelled = True
                    break
                rpath = posixpath.join(base, n)
                local_path = self.ft_local_cwd / n
                one_dl = [sc.parse_download_arg(f"{rpath}:{local_path}")]
                cur += 1
                self._ft_set_download_progress(
                    cur - 1,
                    total,
                    f"{tag} {n} ({cur}/{total})",
                )
                self._ft_begin_transfer_ops(iid, ch)
                try:
                    ok, det = sc.run_ops_on_open_shell(
                        ch,
                        [],
                        [],
                        one_dl,
                        300.0,
                        lg,
                        lg,
                        download_timeout=dl_sec,
                        cancel_event=self.ft_transfer_cancel_event,
                    )
                finally:
                    self._ft_end_transfer_ops()
                self._ft_set_download_progress(cur, total, f"{tag} done {cur}/{total}")
                if not ok:
                    all_ok = False
                    if det == "cancelled":
                        cancelled = True
                        break
                    failures.append(f"{tag} download {rpath}: {det}")
                if getattr(ch, "closed", False):
                    lk2 = self._ft_lock_for(iid)
                    with lk2:
                        if self.ft_sessions.get(iid) is ch:
                            self.ft_sessions.pop(iid, None)
                    self._ft_set_conn_status(iid, "Disconnected")
                    failures.append(f"{tag} session closed; remaining downloads skipped.")
                    break

            def _done() -> None:
                self._ft_log(f"{tag} {'OK' if (all_ok and not failures and not cancelled) else 'finished with issues'}")
                if not cancelled and names and all_ok and not failures:
                    messagebox.showinfo("Download", "All selected files downloaded successfully.")
                elif failures:
                    self._ft_show_failures_dialog("Download failures", failures)
                if not cancelled and names:
                    self._ft_refresh_local_list()

            self.root.after(0, _done)
        finally:
            self.root.after(0, lambda: self._ft_set_busy(False))

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
