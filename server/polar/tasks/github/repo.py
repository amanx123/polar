import structlog

from polar import actions
from polar.ext.sqlalchemy.types import GUID
from polar.models import Organization, Repository
from polar.postgres import AsyncSession
from polar.worker import asyncify_task, task

log = structlog.get_logger()


async def get_organization_and_repo(
    session: AsyncSession,
    organization_id: GUID,
    repository_id: GUID,
) -> tuple[Organization, Repository]:
    organization = await actions.github_organization.get(session, organization_id)
    if not organization:
        log.warning("no organization found", organization_id=organization_id)
        raise ValueError("no organization found")

    repository = await actions.github_repository.get(session, repository_id)
    if not repository:
        log.warning("no repository found", repository_id=organization_id)
        raise ValueError("no repository found")

    return (organization, repository)


@task(name="github.repo.sync.issues")
@asyncify_task(with_session=True)
async def sync_repository_issues(
    session: AsyncSession,
    organization_id: GUID,
    repository_id: GUID,
) -> None:
    organization, repository = await get_organization_and_repo(
        session, organization_id, repository_id
    )
    await actions.github_repository.sync_issues(session, organization, repository)


@task(name="github.repo.sync.pull_requests")
@asyncify_task(with_session=True)
async def sync_repository_pull_requests(
    session: AsyncSession,
    organization_id: GUID,
    repository_id: GUID,
) -> None:
    organization, repository = await get_organization_and_repo(
        session, organization_id, repository_id
    )
    await actions.github_repository.sync_pull_requests(
        session, organization, repository
    )


@task(name="github.repo.sync")
@asyncify_task(with_session=True)
async def sync_repository(
    session: AsyncSession,
    organization_id: GUID,
    repository_id: GUID,
) -> None:
    # TODO: A bit silly to call a task scheduling... tasks.
    # Should the invocation of this function skip .delay?
    sync_repository_issues.delay(organization_id, repository_id)
    sync_repository_pull_requests.delay(organization_id, repository_id)
