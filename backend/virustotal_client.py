"""
VirusTotal Integration Module

Provides threat intelligence lookup capabilities using VirusTotal API v3.
Supports scanning: IP addresses, domains, URLs, and file hashes.
"""

import requests
import os
from typing import Dict, Any, Optional
from datetime import datetime, timezone

class VirusTotalClient:
    """VirusTotal API v3 Client"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('VIRUSTOTAL_API_KEY', '')
        self.base_url = 'https://www.virustotal.com/api/v3'
        self.headers = {
            'x-apikey': self.api_key,
            'Accept': 'application/json'
        }
    
    def is_configured(self) -> bool:
        """Check if VirusTotal API key is configured"""
        return bool(self.api_key and self.api_key != '')
    
    def scan_ip(self, ip_address: str) -> Dict[str, Any]:
        """
        Scan an IP address
        
        Args:
            ip_address: IPv4 or IPv6 address
            
        Returns:
            Dict with scan results
        """
        if not self.is_configured():
            return self._mock_result(ip_address, 'ip')
        
        try:
            url = f"{self.base_url}/ip_addresses/{ip_address}"
            response = requests.get(url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return self._parse_result(data, ip_address, 'ip')
            elif response.status_code == 404:
                return self._not_found_result(ip_address, 'ip')
            else:
                return self._error_result(f"API returned {response.status_code}")
                
        except Exception as e:
            return self._error_result(str(e))
    
    def scan_domain(self, domain: str) -> Dict[str, Any]:
        """Scan a domain name"""
        if not self.is_configured():
            return self._mock_result(domain, 'domain')
        
        try:
            url = f"{self.base_url}/domains/{domain}"
            response = requests.get(url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return self._parse_result(data, domain, 'domain')
            elif response.status_code == 404:
                return self._not_found_result(domain, 'domain')
            else:
                return self._error_result(f"API returned {response.status_code}")
                
        except Exception as e:
            return self._error_result(str(e))
    
    def scan_url(self, url: str) -> Dict[str, Any]:
        """Scan a URL"""
        if not self.is_configured():
            return self._mock_result(url, 'url')
        
        try:
            import base64
            # URL needs to be base64 encoded (without padding)
            url_id = base64.urlsafe_b64encode(url.encode()).decode().strip('=')
            api_url = f"{self.base_url}/urls/{url_id}"
            response = requests.get(api_url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return self._parse_result(data, url, 'url')
            elif response.status_code == 404:
                # URL not in database, submit for scanning
                return self._submit_url(url)
            else:
                return self._error_result(f"API returned {response.status_code}")
                
        except Exception as e:
            return self._error_result(str(e))
    
    def scan_file_hash(self, file_hash: str) -> Dict[str, Any]:
        """Scan a file hash (MD5, SHA1, or SHA256)"""
        if not self.is_configured():
            return self._mock_result(file_hash, 'hash')
        
        try:
            url = f"{self.base_url}/files/{file_hash}"
            response = requests.get(url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return self._parse_result(data, file_hash, 'hash')
            elif response.status_code == 404:
                return self._not_found_result(file_hash, 'hash')
            else:
                return self._error_result(f"API returned {response.status_code}")
                
        except Exception as e:
            return self._error_result(str(e))
    
    def _submit_url(self, url: str) -> Dict[str, Any]:
        """Submit a URL for scanning"""
        try:
            api_url = f"{self.base_url}/urls"
            data = {'url': url}
            response = requests.post(api_url, headers=self.headers, data=data, timeout=10)
            
            if response.status_code == 200:
                return {
                    'artifact': url,
                    'type': 'url',
                    'verdict': 'Pending',
                    'detectionRatio': '0/0',
                    'scanDate': datetime.now(timezone.utc).isoformat(),
                    'message': 'URL submitted for scanning. Check back in a few minutes.'
                }
            else:
                return self._error_result(f"Submission failed: {response.status_code}")
        except Exception as e:
            return self._error_result(str(e))
    
    def _parse_result(self, data: Dict, artifact: str, artifact_type: str) -> Dict[str, Any]:
        """Parse VirusTotal API response"""
        try:
            attributes = data.get('data', {}).get('attributes', {})
            stats = attributes.get('last_analysis_stats', {})
            
            malicious = stats.get('malicious', 0)
            suspicious = stats.get('suspicious', 0)
            harmless = stats.get('harmless', 0)
            undetected = stats.get('undetected', 0)
            
            total = malicious + suspicious + harmless + undetected
            detections = malicious + suspicious
            
            # Determine verdict
            if malicious > 0:
                verdict = 'Malicious'
            elif suspicious > 0:
                verdict = 'Suspicious'
            else:
                verdict = 'Harmless'
            
            return {
                'artifact': artifact,
                'type': artifact_type,
                'verdict': verdict,
                'detectionRatio': f"{detections}/{total}",
                'malicious': malicious,
                'suspicious': suspicious,
                'harmless': harmless,
                'undetected': undetected,
                'scanDate': attributes.get('last_analysis_date', datetime.now(timezone.utc).timestamp()),
                'reputation': attributes.get('reputation', 0),
                'details': attributes
            }
        except Exception as e:
            return self._error_result(f"Parse error: {str(e)}")
    
    def _not_found_result(self, artifact: str, artifact_type: str) -> Dict[str, Any]:
        """Result for artifact not found in VT database"""
        return {
            'artifact': artifact,
            'type': artifact_type,
            'verdict': 'Unknown',
            'detectionRatio': '0/0',
            'scanDate': datetime.now(timezone.utc).isoformat(),
            'message': 'Artifact not found in VirusTotal database'
        }
    
    def _error_result(self, error: str) -> Dict[str, Any]:
        """Result for API errors"""
        return {
            'error': error,
            'verdict': 'Error',
            'scanDate': datetime.now(timezone.utc).isoformat()
        }
    
    def _mock_result(self, artifact: str, artifact_type: str) -> Dict[str, Any]:
        """Mock result when API key not configured"""
        return {
            'artifact': artifact,
            'type': artifact_type,
            'verdict': 'Harmless',
            'detectionRatio': '0/70',
            'malicious': 0,
            'suspicious': 0,
            'harmless': 70,
            'undetected': 0,
            'scanDate': datetime.now(timezone.utc).isoformat(),
            'reputation': 0,
            'message': 'MOCK DATA: VirusTotal API key not configured. Set VIRUSTOTAL_API_KEY environment variable.'
        }


# Singleton instance
_vt_client: Optional[VirusTotalClient] = None

def get_virustotal_client() -> VirusTotalClient:
    """Get or create VirusTotal client singleton"""
    global _vt_client
    if _vt_client is None:
        _vt_client = VirusTotalClient()
    return _vt_client
