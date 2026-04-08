import requests
import time
import json

API_KEY = "<api_key>"
URL = "https://libraries.io/api/search"
PLATFORM = "maven"
PER_PAGE = 100
TIMEOUT = 60

def remove_versions(package):
	if "versions" in package:
		del package["versions"]
	return package

def check_response(url, params):
	while True:
		try: 
			r = requests.get(url, params = params, timeout = TIMEOUT)
			rate_limit_remaining = r.headers.get("X-RateLimit-Remaining")
			limit = r.headers.get("X-RateLimit-Limit")
			if rate_limit_remaining is not None:
				print(f"Remaining call:{rate_limit_remaining}, Limit = {limit}")
			if r.status_code == 200:
				return r.json()
			if r.status_code == 429:
				print("Response : 429, Sleeping.....................:)")
				time.sleep(1800.0)
				print("Waking Up.....................:)")
				continue
			if r.status_code == 403:
				print("Response : 403, Sleeping.....................:)")
				time.sleep(3600.0)
				print("Waking Up.....................:)")
				continue			
			print("Error.....", r.status_code, r.text)
			time.sleep(5.0)
		except requests.exceptions.Timeout:
			print("Timeout while contacting libraries.io. Sleeping....." )
			time.sleep(10)
			print("Retrying....")
			continue
		except requests.exceptions.RequestException as e:
			print(f"Request failed : {e}")
			time.sleep(10)
			print("Retrying....")
			continue
		
def get_top_n(n):
	all_packages = []
	all_responses = []
	page = 1
	while len(all_packages) < n:
		# remaining = n - len(all_packages)
		params = {
			"platforms" : PLATFORM,
			"sort" : "dependents_count",
			"per_page": PER_PAGE,
			"page": page,
			"api_key": API_KEY,
		}
		data = check_response(URL, params)
		all_responses.append(data)
		if not data:
			print("No more results.....")
			break
		all_packages.extend(data)
		if len(data)< PER_PAGE:
			print("Last page..........")
			break
		page += 1
		time.sleep(1.0)
	return all_packages[:n], all_responses

if __name__ == "__main__":
	N = 10000
	packages, responses = get_top_n(N)
	pkg = [remove_versions(p) for p in packages]
	with open("maven_top_n.json", "w", encoding = "utf-8") as f:
		json.dump(pkg, f, indent = 2, ensure_ascii = False)
	with open("maven_all_responses.json", "w", encoding = "utf-8") as f:
		json.dump(responses, f, indent = 2, ensure_ascii = False)
	print("Complete...Saved",len(packages),"packages in maven_top_n.json")
