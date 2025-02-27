import git
import os
import time
import tempfile
import shutil
import logging
import github

# from .utils import tmp_directory

LOGGER = logging.getLogger("conda_forge_webservices.feedstocks_service")


def handle_feedstock_event(org_name, repo_name):
    if repo_name.endswith("-feedstock"):
        update_feedstock(org_name, repo_name)
        return True
    return False


def update_feedstock(org_name, repo_name):
    name = repo_name[:-len("-feedstock")]

    tmp_dir = None
    try:
        tmp_dir = tempfile.mkdtemp('_recipe')

        t0 = time.time()
        feedstocks_url = (
            "https://x-access-token:{}@github.com/conda-forge/feedstocks.git"
            "".format(os.environ["FEEDSTOCKS_GH_TOKEN"])
        )
        feedstocks_repo = git.Repo.clone_from(
            feedstocks_url,
            tmp_dir,
            depth=1,
        )
        LOGGER.info("    update clone: %s", time.time() - t0)

        t0 = time.time()
        # Get the submodule
        # sometimes the webhook outpaces other bits of the API so we try a bit
        for i in range(5):
            try:
                gh = github.Github(os.environ["FEEDSTOCKS_GH_TOKEN"])
                default_branch = (
                    gh
                    .get_repo("{}/{}".format(org_name, repo_name))
                    .default_branch
                )
                break
            except Exception as e:
                if i < 4:
                    time.sleep(0.050 * 2**i)
                    continue
                else:
                    raise e

        feedstock_submodule = feedstocks_repo.create_submodule(
            name=name,
            path=os.path.join("feedstocks", name),
            url="https://github.com/{0}/{1}.git".format(org_name, repo_name),
            branch=default_branch,
        )

        # Update the feedstocks submodule
        with feedstock_submodule.config_writer() as cfg:
            cfg.config.set_value(
                'submodule "%s"' % name,
                "branch",
                "refs/heads/%s" % default_branch,
            )
        feedstock_submodule.update(
            init=True,
            recursive=False,
            force=True,
            to_latest_revision=True
        )
        feedstocks_repo.git.add([".gitmodules", feedstock_submodule.path])
        LOGGER.info("    update submodule: %s", time.time() - t0)

        t0 = time.time()
        # Submit changes
        if feedstocks_repo.is_dirty(working_tree=False, untracked_files=True):
            author = git.Actor(
                "conda-forge-coordinator", "conda.forge.coordinator@gmail.com"
            )
            feedstocks_repo.index.commit(
                "Updated the {0} feedstock.".format(name),
                author=author,
                committer=author
            )
            feedstocks_repo.remote().pull(rebase=True)
            feedstocks_repo.remote().push()
        LOGGER.info("    update push: %s", time.time() - t0)

    finally:
        if tmp_dir is not None:
            shutil.rmtree(tmp_dir)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('org')
    parser.add_argument('repo')
    args = parser.parse_args()
    update_feedstock(args.org, args.repo)
