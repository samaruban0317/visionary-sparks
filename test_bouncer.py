import requests

# 1. The local web address where your bouncer server is listening
url = "http://127.0.0.1:8000/bouncer"

# 2. This is the package of data the student's phone sends
payload = {
    "user_id": "student_test_01",
    "raw_prompt": "Please urgently help! I don't get physics at all.",
    "subject": "physics"
}

print("🚀 Launching test prompt to the Bouncer...")

# 3. Shoot the payload over the local network to the server
response = requests.post(url, json=payload)

# 4. Print the final decision your backend server made
print("📊 Server Decision:")
print(response.json())