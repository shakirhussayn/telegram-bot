import requests
import json

# Your API key
FACESWAP_API_KEY = "cmc78va30000qlb042tlt1i01"

# The correct endpoint from the curl example
url = "https://api.magicapi.dev/api/v1/magicapi/faceswap-v2/faceswap/image/run"

headers = {
    'accept': 'application/json',
    'x-magicapi-key': FACESWAP_API_KEY,
    'Content-Type': 'application/json'
}

# Test data
data = {
    "input": {
        "swap_image": "https://blog.api.market/wp-content/uploads/2024/06/Elon_Musk.png",
        "target_image": "https://blog.api.market/wp-content/uploads/2024/06/Shahrukh_khan.png"
    }
}

print("Testing the correct FaceSwap API endpoint...")
print(f"URL: {url}")
print(f"API Key: {FACESWAP_API_KEY}")
print("="*70)

try:
    response = requests.post(url, headers=headers, json=data, timeout=30)
    
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        print("SUCCESS! The API call worked!")
        try:
            json_response = response.json()
            print(f"Response: {json.dumps(json_response, indent=2)}")
            
            if 'id' in json_response:
                job_id = json_response['id']
                print(f"Job ID: {job_id}")
                print("Your API key and endpoint are working correctly!")
                
                # Test the status endpoint
                status_url = f"https://api.magicapi.dev/api/v1/magicapi/faceswap-v2/faceswap/image/status/{job_id}"
                print(f"\nTesting status endpoint...")
                
                status_headers = {
                    'accept': 'application/json',
                    'x-magicapi-key': FACESWAP_API_KEY
                }
                
                status_response = requests.get(status_url, headers=status_headers)
                print(f"Status Check: {status_response.status_code}")
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    print(f"Status Response: {json.dumps(status_data, indent=2)}")
                
        except json.JSONDecodeError:
            print(f"Response is not JSON: {response.text}")
            
    elif response.status_code == 401:
        print("ERROR: 401 Unauthorized")
        print("Your API key is invalid")
        
    elif response.status_code == 403:
        print("ERROR: 403 Forbidden") 
        print("No subscription or insufficient permissions")
        
    elif response.status_code == 404:
        print("ERROR: 404 Not Found")
        print("Endpoint not found")
        
    elif response.status_code == 422:
        print("ERROR: 422 Unprocessable Entity")
        print("Invalid request data")
        print(f"Response: {response.text}")
        
    else:
        print(f"ERROR: Status code {response.status_code}")
        print(f"Response: {response.text}")
        
except requests.exceptions.Timeout:
    print("ERROR: Request timed out")
except requests.exceptions.ConnectionError:
    print("ERROR: Connection failed")
except Exception as e:
    print(f"ERROR: {str(e)}")

print("\n" + "="*70)
