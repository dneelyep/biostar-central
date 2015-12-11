from github import Github
from biostar.apps.posts.models import Post
from biostar.apps.users.models import User

class GithubIssueConnector():
    """Provides capabilities for connecting to Biostars github accounts."""

    GITHUB_USER_NAME = "TODOUserNameHere"
    GITHUB_PASSWORD = "TODOPasswordHere"

    BIOSTAR_CENTRAL_REPO_ACCOUNT = "ialbert"
    BIOSTAR_CENTRAL_REPO_NAME = "biostar-central"

    def add_posts_for_issues(self):
        g = Github(self.GITHUB_USER_NAME, self.GITHUB_PASSWORD)
        biostar_central_repo = g.get_user(self.BIOSTAR_CENTRAL_REPO_ACCOUNT).get_repo(self.BIOSTAR_CENTRAL_REPO_NAME)
        biostar_central_issues = biostar_central_repo.get_issues()

        for issue in biostar_central_issues:
            title = issue.title
            content = issue.body + "\n" + issue.html_url
            post_type = Post.QUESTION
            tag_val = 'from-github,github-issue-#' + str(issue.number)

            post = Post(title=title, content=content, tag_val=tag_val, author=User.objects.get(email="TODOGetCurrentUserHere"),
                        type=post_type)
            post.save()