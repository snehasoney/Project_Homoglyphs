import requests
import json
import time 

TOKEN = "github_token"
URL = "https://api.github.com/graphql"

query = """
query($cursor: String, $queryString: String!) {
  rateLimit {
    limit
    remaining
    used
    resetAt
    cost
  }
  search(
    query: $queryString,
    type: REPOSITORY,
    first: 100,
    after: $cursor
  ) {
    pageInfo {
      endCursor
      hasNextPage
    }
    nodes {
      ... on Repository {
        nameWithOwner
        stargazerCount
        url
      }
    }
  }
}
"""

headers = {"Authorization": f"Bearer {TOKEN}"}

def check_response(data):
	while True:
		r = requests.post(URL, json=data, headers=headers)
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

def get_top_1000_repos(q,remaining,responses_list):
	repos = []
	cursor = None
	min_star = None 
	search_count = min(remaining, 1000)
	while len(repos) < search_count:
		variables = {"cursor": cursor,"queryString": q,}
		result = check_response({"query":query, "variables":variables})
		responses_list.append(result)
		if "errors" in result:
			print("Error.....")
			print(json.dumps(result["errors"], indent=2))
			break
		rate = result["data"]["rateLimit"]
		print(f"Rate Limit : remaining ={rate['remaining']} cost={rate['cost']}")
		search = result["data"]["search"]
		pageInfo = search["pageInfo"]
		nodes = search["nodes"]
		for repo in nodes:
			repos.append(repo)
			stars=repo["stargazerCount"]
			if min_star is None or stars < min_star:
				min_star = stars
			if len(repos)>=search_count:
				break
		if not pageInfo["hasNextPage"]:
			print("No more pages")
			break
		cursor=pageInfo["endCursor"]
		time.sleep(5.0)
	return repos, min_star
	
def get_top_n_repos(n):
	all_repos = {}
	all_responses = []
	offset = None
	while len(all_repos) < n:
		remaining = n - len(all_repos)
		if offset is None:
			q = "stars:>0 sort:stars-desc"
		else:
			q = f"stars:<{offset} sort:stars-desc"
		print(f".....New batch.....Query:'{q}'.....Remaining = {remaining}")
		batch, min_stars = get_top_1000_repos(q, remaining, all_responses)
		if not batch:
			print("Got empty batch...Breaking")
			break
		for repo in batch:
			name = repo["nameWithOwner"]
			if(name not in all_repos or repo["stargazerCount"] > all_repos[name]["stargazerCount"]):
				all_repos[name] = repo
		print(f"........Collected {len(all_repos)} unique repos........")
		offset = min_stars
		if len(all_repos) >= n:
			break
	repo_list = list(all_repos.values())
	repo_list.sort(key=lambda r: r["stargazerCount"], reverse = True)
	return repo_list[:n], all_responses
			
if __name__ == "__main__":
	N = 10000
	repos, responses = get_top_n_repos(N)
	with open("top_n.json","w",encoding = "utf-8") as f:
		json.dump(repos, f, ensure_ascii = False, indent =2)
	with open("responses.json", "w", encoding="utf-8") as f:
		json.dump(responses, f, ensure_ascii = False, indent =2)
	print("Complete...Saved",len(repos),"repositories in top_n.json")
