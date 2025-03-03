import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from pytest_mock import MockerFixture

from polar.auth.models import AuthSubject
from polar.authz.service import Authz
from polar.enums import SubscriptionRecurringInterval
from polar.exceptions import NotPermitted, PolarRequestValidationError
from polar.kit.pagination import PaginationParams
from polar.models import Benefit, File, Organization, Product, User, UserOrganization
from polar.models.benefit import BenefitType
from polar.models.file import FileServiceTypes
from polar.models.product_price import (
    ProductPriceAmountType,
    ProductPriceFixed,
    ProductPriceType,
)
from polar.postgres import AsyncSession
from polar.product.schemas import (
    ExistingProductPrice,
    ProductCreate,
    ProductOneTimeCreate,
    ProductPriceOneTimeCustomCreate,
    ProductPriceOneTimeFixedCreate,
    ProductPriceOneTimeFreeCreate,
    ProductPriceRecurringFixedCreate,
    ProductPriceRecurringFreeCreate,
    ProductRecurringCreate,
    ProductUpdate,
)
from polar.product.service.product import product as product_service
from polar.product.sorting import ProductSortProperty
from tests.fixtures.auth import AuthSubjectFixture
from tests.fixtures.database import SaveFixture
from tests.fixtures.random_objects import (
    create_benefit,
    create_product,
    set_product_benefits,
)


@pytest.fixture
def authz(session: AsyncSession) -> Authz:
    return Authz(session)


@pytest.fixture
def enqueue_job_mock(mocker: MockerFixture) -> AsyncMock:
    return mocker.patch("polar.product.service.product.enqueue_job")


@pytest.mark.asyncio
class TestList:
    @pytest.mark.auth
    async def test_user(
        self,
        auth_subject: AuthSubject[User],
        session: AsyncSession,
        products: list[Product],
        user: User,
    ) -> None:
        # then
        session.expunge_all()

        results, count = await product_service.list(
            session,
            auth_subject,
            pagination=PaginationParams(1, 10),
        )

        assert count == 0
        assert len(results) == 0

    @pytest.mark.auth
    async def test_user_organization(
        self,
        auth_subject: AuthSubject[User],
        session: AsyncSession,
        products: list[Product],
        user_organization: UserOrganization,
    ) -> None:
        # then
        session.expunge_all()

        results, count = await product_service.list(
            session,
            auth_subject,
            pagination=PaginationParams(1, 10),
        )

        assert count == 2
        assert len(results) == 2

    @pytest.mark.auth(AuthSubjectFixture(subject="organization"))
    async def test_organization(
        self,
        auth_subject: AuthSubject[Organization],
        session: AsyncSession,
        products: list[Product],
    ) -> None:
        # then
        session.expunge_all()

        results, count = await product_service.list(
            session, auth_subject, pagination=PaginationParams(1, 10)
        )

        assert count == 2
        assert len(results) == 2

    @pytest.mark.auth
    async def test_filter_is_recurring(
        self,
        auth_subject: AuthSubject[User],
        session: AsyncSession,
        save_fixture: SaveFixture,
        organization: Organization,
        user_organization: UserOrganization,
    ) -> None:
        recurring_product = await create_product(
            save_fixture,
            organization=organization,
        )
        one_time_product = await create_product(
            save_fixture,
            organization=organization,
            prices=[
                (1000, ProductPriceType.one_time, None),
            ],
        )

        # then
        session.expunge_all()

        results, count = await product_service.list(
            session,
            auth_subject,
            organization_id=[recurring_product.organization_id],
            is_recurring=True,
            pagination=PaginationParams(1, 10),
        )

        assert count == 1
        assert len(results) == 1
        assert results[0].id == recurring_product.id

        results, count = await product_service.list(
            session,
            auth_subject,
            organization_id=[recurring_product.organization_id],
            is_recurring=False,
            pagination=PaginationParams(1, 10),
        )

        assert count == 1
        assert len(results) == 1
        assert results[0].id == one_time_product.id

    @pytest.mark.auth
    async def test_filter_organization(
        self,
        auth_subject: AuthSubject[User],
        session: AsyncSession,
        organization: Organization,
        products: list[Product],
        product: Product,
        product_second: Product,
        user_organization: UserOrganization,
    ) -> None:
        # then
        session.expunge_all()

        results, count = await product_service.list(
            session,
            auth_subject,
            organization_id=[organization.id],
            pagination=PaginationParams(1, 10),
            sorting=[(ProductSortProperty.created_at, False)],
        )

        assert count == 2
        assert len(results) == 2
        assert results[0].id == product.id
        assert results[1].id == product_second.id

    @pytest.mark.auth
    async def test_filter_is_archived(
        self,
        auth_subject: AuthSubject[User],
        session: AsyncSession,
        save_fixture: SaveFixture,
        user: User,
        organization: Organization,
        user_organization: UserOrganization,
    ) -> None:
        archived_product = await create_product(
            save_fixture, organization=organization, is_archived=True
        )

        # then
        session.expunge_all()

        results, count = await product_service.list(
            session,
            auth_subject,
            organization_id=[archived_product.organization_id],
            is_archived=False,
            pagination=PaginationParams(1, 10),
        )
        assert count == 0
        assert len(results) == 0
        results, count = await product_service.list(
            session,
            auth_subject,
            organization_id=[archived_product.organization_id],
            pagination=PaginationParams(1, 10),
        )
        assert count == 1
        assert len(results) == 1
        assert results[0].id == archived_product.id

    @pytest.mark.auth
    async def test_filter_benefit_id(
        self,
        save_fixture: SaveFixture,
        auth_subject: AuthSubject[User],
        session: AsyncSession,
        organization: Organization,
        products: list[Product],
        benefit_organization: Benefit,
        benefit_organization_second: Benefit,
        user_organization: UserOrganization,
    ) -> None:
        for product in products[:2]:
            await set_product_benefits(
                save_fixture,
                product=product,
                benefits=[benefit_organization, benefit_organization_second],
            )

        # then
        session.expunge_all()

        results, count = await product_service.list(
            session,
            auth_subject,
            organization_id=[organization.id],
            benefit_id=[benefit_organization.id],
            pagination=PaginationParams(1, 10),
            sorting=[(ProductSortProperty.created_at, False)],
        )

        assert count == 2
        assert len(results) == 2
        assert results[0].id == products[0].id
        assert results[1].id == products[1].id


@pytest.mark.asyncio
class TestGetById:
    @pytest.mark.auth
    async def test_user(
        self,
        auth_subject: AuthSubject[User],
        session: AsyncSession,
        product: Product,
    ) -> None:
        # then
        session.expunge_all()

        retrieved_product = await product_service.get_by_id(
            session, auth_subject, product.id
        )
        assert retrieved_product is None

    @pytest.mark.auth
    async def test_user_organization(
        self,
        auth_subject: AuthSubject[User],
        session: AsyncSession,
        product: Product,
        user: User,
        user_organization: UserOrganization,
    ) -> None:
        # then
        session.expunge_all()

        not_existing_product = await product_service.get_by_id(
            session, auth_subject, uuid.uuid4()
        )
        assert not_existing_product is None

        accessible_product = await product_service.get_by_id(
            session, auth_subject, product.id
        )
        assert accessible_product is not None
        assert accessible_product.id == product.id

    @pytest.mark.auth(AuthSubjectFixture(subject="organization"))
    async def test_organization(
        self,
        auth_subject: AuthSubject[Organization],
        session: AsyncSession,
        product: Product,
    ) -> None:
        # then
        session.expunge_all()

        not_existing_product = await product_service.get_by_id(
            session, auth_subject, uuid.uuid4()
        )
        assert not_existing_product is None

        accessible_product = await product_service.get_by_id(
            session, auth_subject, product.id
        )
        assert accessible_product is not None
        assert accessible_product.id == product.id


@pytest.mark.asyncio
@pytest.mark.skip_db_asserts
class TestCreate:
    @pytest.mark.auth
    async def test_user_not_existing_organization(
        self, auth_subject: AuthSubject[User], session: AsyncSession, authz: Authz
    ) -> None:
        create_schema = ProductRecurringCreate(
            name="Product",
            organization_id=uuid.uuid4(),
            prices=[
                ProductPriceRecurringFixedCreate(
                    type=ProductPriceType.recurring,
                    amount_type=ProductPriceAmountType.fixed,
                    recurring_interval=SubscriptionRecurringInterval.month,
                    price_amount=1000,
                    price_currency="usd",
                )
            ],
        )

        with pytest.raises(PolarRequestValidationError):
            await product_service.create(session, authz, create_schema, auth_subject)

    @pytest.mark.auth
    async def test_user_not_writable_organization(
        self,
        auth_subject: AuthSubject[User],
        session: AsyncSession,
        authz: Authz,
        organization: Organization,
    ) -> None:
        create_schema = ProductRecurringCreate(
            name="Product",
            organization_id=organization.id,
            prices=[
                ProductPriceRecurringFixedCreate(
                    type=ProductPriceType.recurring,
                    amount_type=ProductPriceAmountType.fixed,
                    recurring_interval=SubscriptionRecurringInterval.month,
                    price_amount=1000,
                    price_currency="usd",
                )
            ],
        )

        with pytest.raises(NotPermitted):
            await product_service.create(session, authz, create_schema, auth_subject)

    @pytest.mark.auth
    async def test_user_valid_organization(
        self,
        auth_subject: AuthSubject[User],
        session: AsyncSession,
        authz: Authz,
        organization: Organization,
        user_organization: UserOrganization,
        stripe_service_mock: MagicMock,
    ) -> None:
        create_product_mock: MagicMock = stripe_service_mock.create_product
        create_product_mock.return_value = SimpleNamespace(id="PRODUCT_ID")

        create_price_for_product_mock: MagicMock = (
            stripe_service_mock.create_price_for_product
        )
        create_price_for_product_mock.return_value = SimpleNamespace(id="PRICE_ID")

        create_schema = ProductRecurringCreate(
            name="Product",
            organization_id=organization.id,
            prices=[
                ProductPriceRecurringFixedCreate(
                    type=ProductPriceType.recurring,
                    amount_type=ProductPriceAmountType.fixed,
                    recurring_interval=SubscriptionRecurringInterval.month,
                    price_amount=1000,
                    price_currency="usd",
                )
            ],
        )

        product = await product_service.create(
            session, authz, create_schema, auth_subject
        )
        assert product.organization_id == organization.id

        create_product_mock.assert_called_once()
        create_price_for_product_mock.assert_called_once()
        assert product.stripe_product_id == "PRODUCT_ID"

        assert len(product.prices) == 1
        assert product.prices[0].stripe_price_id == "PRICE_ID"

    @pytest.mark.auth
    async def test_user_empty_description(
        self,
        auth_subject: AuthSubject[User],
        session: AsyncSession,
        authz: Authz,
        organization: Organization,
        user_organization: UserOrganization,
        stripe_service_mock: MagicMock,
    ) -> None:
        create_product_mock: MagicMock = stripe_service_mock.create_product
        create_product_mock.return_value = SimpleNamespace(id="PRODUCT_ID")
        create_price_for_product_mock: MagicMock = (
            stripe_service_mock.create_price_for_product
        )
        create_price_for_product_mock.return_value = SimpleNamespace(id="PRICE_ID")

        create_schema = ProductRecurringCreate(
            name="Product",
            description="",
            organization_id=organization.id,
            prices=[
                ProductPriceRecurringFixedCreate(
                    type=ProductPriceType.recurring,
                    amount_type=ProductPriceAmountType.fixed,
                    recurring_interval=SubscriptionRecurringInterval.month,
                    price_amount=1000,
                    price_currency="usd",
                )
            ],
        )

        product = await product_service.create(
            session, authz, create_schema, auth_subject
        )
        assert product.description is None

    @pytest.mark.auth(AuthSubjectFixture(subject="organization"))
    async def test_organization_set_organization_id(
        self,
        auth_subject: AuthSubject[Organization],
        session: AsyncSession,
        authz: Authz,
        organization: Organization,
    ) -> None:
        create_schema = ProductRecurringCreate(
            name="Product",
            organization_id=organization.id,
            prices=[
                ProductPriceRecurringFixedCreate(
                    type=ProductPriceType.recurring,
                    amount_type=ProductPriceAmountType.fixed,
                    recurring_interval=SubscriptionRecurringInterval.month,
                    price_amount=1000,
                    price_currency="usd",
                )
            ],
        )

        with pytest.raises(PolarRequestValidationError):
            await product_service.create(session, authz, create_schema, auth_subject)

    @pytest.mark.auth(AuthSubjectFixture(subject="organization"))
    async def test_organization_valid(
        self,
        auth_subject: AuthSubject[Organization],
        session: AsyncSession,
        authz: Authz,
        organization: Organization,
        stripe_service_mock: MagicMock,
    ) -> None:
        create_product_mock: MagicMock = stripe_service_mock.create_product
        create_product_mock.return_value = SimpleNamespace(id="PRODUCT_ID")

        create_price_for_product_mock: MagicMock = (
            stripe_service_mock.create_price_for_product
        )
        create_price_for_product_mock.return_value = SimpleNamespace(id="PRICE_ID")

        create_schema = ProductRecurringCreate(
            name="Product",
            prices=[
                ProductPriceRecurringFixedCreate(
                    type=ProductPriceType.recurring,
                    amount_type=ProductPriceAmountType.fixed,
                    recurring_interval=SubscriptionRecurringInterval.month,
                    price_amount=1000,
                    price_currency="usd",
                )
            ],
        )

        product = await product_service.create(
            session, authz, create_schema, auth_subject
        )
        assert product.organization_id == organization.id

    @pytest.mark.auth
    async def test_not_existing_media(
        self,
        auth_subject: AuthSubject[Organization],
        session: AsyncSession,
        authz: Authz,
        organization: Organization,
        user_organization: UserOrganization,
        stripe_service_mock: MagicMock,
    ) -> None:
        create_product_mock: MagicMock = stripe_service_mock.create_product
        create_price_for_product_mock: MagicMock = (
            stripe_service_mock.create_price_for_product
        )

        create_schema = ProductRecurringCreate(
            name="Product",
            organization_id=organization.id,
            prices=[
                ProductPriceRecurringFixedCreate(
                    type=ProductPriceType.recurring,
                    amount_type=ProductPriceAmountType.fixed,
                    recurring_interval=SubscriptionRecurringInterval.month,
                    price_amount=1000,
                    price_currency="usd",
                )
            ],
            medias=[uuid.uuid4()],
        )

        with pytest.raises(PolarRequestValidationError):
            await product_service.create(session, authz, create_schema, auth_subject)

        create_product_mock.assert_not_called()
        create_price_for_product_mock.assert_not_called()

    @pytest.mark.auth
    @pytest.mark.parametrize(
        "file_kwargs",
        [
            {"service": FileServiceTypes.downloadable},
            {"is_enabled": False},
            {"is_uploaded": False},
        ],
    )
    async def test_invalid_media(
        self,
        file_kwargs: dict[str, Any],
        save_fixture: SaveFixture,
        auth_subject: AuthSubject[Organization],
        session: AsyncSession,
        authz: Authz,
        organization: Organization,
        user_organization: UserOrganization,
        stripe_service_mock: MagicMock,
    ) -> None:
        file = File(
            **{
                "organization": organization,
                "name": "Product Cover",
                "path": "/product-cover.jpg",
                "mime_type": "image/jpeg",
                "size": 1024,
                "service": FileServiceTypes.product_media,
                "is_enabled": True,
                "is_uploaded": True,
                **file_kwargs,
            }
        )
        await save_fixture(file)

        create_product_mock: MagicMock = stripe_service_mock.create_product
        create_price_for_product_mock: MagicMock = (
            stripe_service_mock.create_price_for_product
        )

        create_schema = ProductRecurringCreate(
            name="Product",
            organization_id=organization.id,
            prices=[
                ProductPriceRecurringFixedCreate(
                    type=ProductPriceType.recurring,
                    amount_type=ProductPriceAmountType.fixed,
                    recurring_interval=SubscriptionRecurringInterval.month,
                    price_amount=1000,
                    price_currency="usd",
                )
            ],
            medias=[file.id],
        )

        with pytest.raises(PolarRequestValidationError):
            await product_service.create(session, authz, create_schema, auth_subject)

        create_product_mock.assert_not_called()
        create_price_for_product_mock.assert_not_called()

    @pytest.mark.auth
    async def test_valid_media(
        self,
        save_fixture: SaveFixture,
        auth_subject: AuthSubject[Organization],
        session: AsyncSession,
        authz: Authz,
        organization: Organization,
        user_organization: UserOrganization,
        stripe_service_mock: MagicMock,
    ) -> None:
        file = File(
            **{
                "organization": organization,
                "name": "Product Cover",
                "path": "/product-cover.jpg",
                "mime_type": "image/jpeg",
                "size": 1024,
                "service": FileServiceTypes.product_media,
                "is_enabled": True,
                "is_uploaded": True,
            }
        )
        await save_fixture(file)

        create_product_mock: MagicMock = stripe_service_mock.create_product
        create_product_mock.return_value = SimpleNamespace(id="PRODUCT_ID")

        create_price_for_product_mock: MagicMock = (
            stripe_service_mock.create_price_for_product
        )
        create_price_for_product_mock.return_value = SimpleNamespace(id="PRICE_ID")

        create_schema = ProductRecurringCreate(
            name="Product",
            organization_id=organization.id,
            prices=[
                ProductPriceRecurringFixedCreate(
                    type=ProductPriceType.recurring,
                    amount_type=ProductPriceAmountType.fixed,
                    recurring_interval=SubscriptionRecurringInterval.month,
                    price_amount=1000,
                    price_currency="usd",
                )
            ],
            medias=[file.id],
        )

        product = await product_service.create(
            session, authz, create_schema, auth_subject
        )

        assert len(product.medias) == 1

    @pytest.mark.parametrize(
        "create_schema",
        (
            ProductOneTimeCreate(
                name="Product",
                prices=[
                    ProductPriceOneTimeFixedCreate(
                        type=ProductPriceType.one_time,
                        amount_type=ProductPriceAmountType.fixed,
                        price_amount=1000,
                        price_currency="usd",
                    )
                ],
            ),
            ProductOneTimeCreate(
                name="Product",
                prices=[
                    ProductPriceOneTimeCustomCreate(
                        type=ProductPriceType.one_time,
                        amount_type=ProductPriceAmountType.custom,
                        minimum_amount=1000,
                        maximum_amount=2000,
                        preset_amount=1500,
                        price_currency="usd",
                    ),
                ],
            ),
            ProductOneTimeCreate(
                name="Product",
                prices=[
                    ProductPriceOneTimeFreeCreate(
                        type=ProductPriceType.one_time,
                        amount_type=ProductPriceAmountType.free,
                    ),
                ],
            ),
            ProductRecurringCreate(
                name="Product",
                prices=[
                    ProductPriceRecurringFreeCreate(
                        type=ProductPriceType.recurring,
                        amount_type=ProductPriceAmountType.free,
                        recurring_interval=SubscriptionRecurringInterval.month,
                    )
                ],
            ),
        ),
    )
    @pytest.mark.auth
    async def test_valid_prices(
        self,
        create_schema: ProductCreate,
        auth_subject: AuthSubject[User],
        session: AsyncSession,
        authz: Authz,
        organization: Organization,
        user_organization: UserOrganization,
        stripe_service_mock: MagicMock,
    ) -> None:
        create_product_mock: MagicMock = stripe_service_mock.create_product
        create_product_mock.return_value = SimpleNamespace(id="PRODUCT_ID")

        create_price_for_product_mock: MagicMock = (
            stripe_service_mock.create_price_for_product
        )
        create_price_for_product_mock.return_value = SimpleNamespace(id="PRICE_ID")

        create_schema.organization_id = organization.id
        product = await product_service.create(
            session, authz, create_schema, auth_subject
        )
        assert product.organization_id == organization.id

        create_product_mock.assert_called_once()
        create_price_for_product_mock.assert_called_once()
        assert product.stripe_product_id == "PRODUCT_ID"

        assert len(product.prices) == 1
        assert product.prices[0].stripe_price_id == "PRICE_ID"


@pytest.mark.asyncio
@pytest.mark.skip_db_asserts
class TestUpdate:
    @pytest.mark.auth
    async def test_not_writable_product(
        self,
        auth_subject: AuthSubject[User],
        session: AsyncSession,
        authz: Authz,
        product: Product,
    ) -> None:
        # load
        product_organization_loaded = await product_service.get_loaded(
            session, product.id
        )
        assert product_organization_loaded

        update_schema = ProductUpdate(name="Product Update")
        with pytest.raises(NotPermitted):
            await product_service.update(
                session,
                authz,
                product_organization_loaded,
                update_schema,
                auth_subject,
            )

    @pytest.mark.auth(
        AuthSubjectFixture(subject="user"),
        AuthSubjectFixture(subject="organization"),
    )
    async def test_no_price(
        self,
        auth_subject: AuthSubject[User],
        session: AsyncSession,
        authz: Authz,
        product: Product,
        user_organization: UserOrganization,
    ) -> None:
        # load
        product_organization_loaded = await product_service.get_loaded(
            session, product.id
        )
        assert product_organization_loaded

        update_schema = ProductUpdate(prices=[])
        with pytest.raises(PolarRequestValidationError):
            await product_service.update(
                session,
                authz,
                product_organization_loaded,
                update_schema,
                auth_subject,
            )

    @pytest.mark.auth(
        AuthSubjectFixture(subject="user"),
        AuthSubjectFixture(subject="organization"),
    )
    async def test_valid_name_change(
        self,
        session: AsyncSession,
        authz: Authz,
        auth_subject: AuthSubject[User | Organization],
        product: Product,
        organization: Organization,
        user_organization: UserOrganization,
        stripe_service_mock: MagicMock,
    ) -> None:
        update_product_mock: MagicMock = stripe_service_mock.update_product

        # load
        product_organization_loaded = await product_service.get_loaded(
            session, product.id
        )
        assert product_organization_loaded

        update_schema = ProductUpdate(name="Product Update")
        updated_product = await product_service.update(
            session,
            authz,
            product_organization_loaded,
            update_schema,
            auth_subject,
        )
        assert updated_product.name == "Product Update"

        update_product_mock.assert_called_once_with(
            updated_product.stripe_product_id,
            name=f"{organization.slug} - Product Update",
        )

    @pytest.mark.auth(
        AuthSubjectFixture(subject="user"),
        AuthSubjectFixture(subject="organization"),
    )
    async def test_valid_description_change(
        self,
        session: AsyncSession,
        authz: Authz,
        auth_subject: AuthSubject[User | Organization],
        product: Product,
        user_organization: UserOrganization,
        stripe_service_mock: MagicMock,
    ) -> None:
        update_product_mock: MagicMock = stripe_service_mock.update_product

        # load
        product_organization_loaded = await product_service.get_loaded(
            session, product.id
        )
        assert product_organization_loaded

        update_schema = ProductUpdate(description="Description update")
        updated_product = await product_service.update(
            session,
            authz,
            product_organization_loaded,
            update_schema,
            auth_subject,
        )
        assert updated_product.description == "Description update"

        update_product_mock.assert_called_once_with(
            updated_product.stripe_product_id,
            description="Description update",
        )

    @pytest.mark.auth(
        AuthSubjectFixture(subject="user"),
        AuthSubjectFixture(subject="organization"),
    )
    async def test_empty_description_update(
        self,
        session: AsyncSession,
        authz: Authz,
        auth_subject: AuthSubject[User | Organization],
        product: Product,
        user_organization: UserOrganization,
        stripe_service_mock: MagicMock,
    ) -> None:
        update_product_mock: MagicMock = stripe_service_mock.update_product

        # load
        product_organization_loaded = await product_service.get_loaded(
            session, product.id
        )
        assert product_organization_loaded

        update_schema = ProductUpdate(description="")
        updated_product = await product_service.update(
            session,
            authz,
            product_organization_loaded,
            update_schema,
            auth_subject,
        )
        assert updated_product.description == product.description

        update_product_mock.assert_not_called()

    @pytest.mark.auth(
        AuthSubjectFixture(subject="user"),
        AuthSubjectFixture(subject="organization"),
    )
    async def test_valid_price_added(
        self,
        session: AsyncSession,
        authz: Authz,
        auth_subject: AuthSubject[User | Organization],
        product: Product,
        user_organization: UserOrganization,
        stripe_service_mock: MagicMock,
    ) -> None:
        create_price_for_product_mock: MagicMock = (
            stripe_service_mock.create_price_for_product
        )
        create_price_for_product_mock.return_value = SimpleNamespace(id="NEW_PRICE_ID")

        # load
        product_organization_loaded = await product_service.get_loaded(
            session, product.id
        )
        assert product_organization_loaded

        update_schema = ProductUpdate(
            prices=[
                ExistingProductPrice(id=product_organization_loaded.prices[0].id),
                ProductPriceRecurringFixedCreate(
                    type=ProductPriceType.recurring,
                    amount_type=ProductPriceAmountType.fixed,
                    recurring_interval=SubscriptionRecurringInterval.year,
                    price_amount=12000,
                    price_currency="usd",
                ),
            ]
        )
        updated_product = await product_service.update(
            session,
            authz,
            product_organization_loaded,
            update_schema,
            auth_subject,
        )

        create_price_for_product_mock.assert_called_once()

        assert len(updated_product.prices) == 2
        assert updated_product.prices[0].id == product_organization_loaded.prices[0].id

        new_price = updated_product.prices[1]
        assert isinstance(new_price, ProductPriceFixed)
        assert new_price.recurring_interval == "year"
        assert new_price.price_amount == 12000
        assert new_price.stripe_price_id == "NEW_PRICE_ID"

    @pytest.mark.auth(
        AuthSubjectFixture(subject="user"),
        AuthSubjectFixture(subject="organization"),
    )
    async def test_valid_price_deleted(
        self,
        session: AsyncSession,
        authz: Authz,
        auth_subject: AuthSubject[User | Organization],
        product: Product,
        user_organization: UserOrganization,
        stripe_service_mock: MagicMock,
    ) -> None:
        create_price_for_product_mock: MagicMock = (
            stripe_service_mock.create_price_for_product
        )
        create_price_for_product_mock.return_value = SimpleNamespace(id="NEW_PRICE_ID")
        archive_price_mock: MagicMock = stripe_service_mock.archive_price

        deleted_price_id = product.prices[0].stripe_price_id

        # load
        product_organization_loaded = await product_service.get_loaded(
            session, product.id
        )
        assert product_organization_loaded

        update_schema = ProductUpdate(
            prices=[
                ProductPriceRecurringFixedCreate(
                    type=ProductPriceType.recurring,
                    amount_type=ProductPriceAmountType.fixed,
                    recurring_interval=SubscriptionRecurringInterval.year,
                    price_amount=12000,
                    price_currency="usd",
                ),
            ]
        )
        updated_product = await product_service.update(
            session,
            authz,
            product_organization_loaded,
            update_schema,
            auth_subject,
        )

        create_price_for_product_mock.assert_called_once()
        archive_price_mock.assert_called_once_with(deleted_price_id)

        assert len(updated_product.prices) == 1

        new_price = updated_product.prices[0]
        assert isinstance(new_price, ProductPriceFixed)
        assert new_price.recurring_interval == "year"
        assert new_price.price_amount == 12000
        assert new_price.stripe_price_id == "NEW_PRICE_ID"

    @pytest.mark.auth(
        AuthSubjectFixture(subject="user"),
        AuthSubjectFixture(subject="organization"),
    )
    async def test_valid_archive(
        self,
        session: AsyncSession,
        authz: Authz,
        auth_subject: AuthSubject[User | Organization],
        product: Product,
        user_organization: UserOrganization,
        stripe_service_mock: MagicMock,
    ) -> None:
        archive_product_mock: MagicMock = stripe_service_mock.archive_product

        # load
        product_organization_loaded = await product_service.get_loaded(
            session, product.id
        )
        assert product_organization_loaded

        update_schema = ProductUpdate(is_archived=True)
        updated_product = await product_service.update(
            session,
            authz,
            product_organization_loaded,
            update_schema,
            auth_subject,
        )

        archive_product_mock.assert_called_once_with(product.stripe_product_id)

        assert updated_product.is_archived

    @pytest.mark.auth(
        AuthSubjectFixture(subject="user"),
        AuthSubjectFixture(subject="organization"),
    )
    async def test_valid_unarchive(
        self,
        session: AsyncSession,
        save_fixture: SaveFixture,
        authz: Authz,
        auth_subject: AuthSubject[User | Organization],
        product: Product,
        user_organization: UserOrganization,
        stripe_service_mock: MagicMock,
    ) -> None:
        product.is_archived = True
        await save_fixture(product)

        unarchive_product: MagicMock = stripe_service_mock.unarchive_product

        # load
        product_organization_loaded = await product_service.get_loaded(
            session, product.id
        )
        assert product_organization_loaded

        update_schema = ProductUpdate(is_archived=False)
        updated_product = await product_service.update(
            session,
            authz,
            product_organization_loaded,
            update_schema,
            auth_subject,
        )

        unarchive_product.assert_called_once_with(product.stripe_product_id)

        assert not updated_product.is_archived

    @pytest.mark.auth(
        AuthSubjectFixture(subject="user"),
        AuthSubjectFixture(subject="organization"),
    )
    async def test_not_existing_media(
        self,
        auth_subject: AuthSubject[User],
        session: AsyncSession,
        authz: Authz,
        product: Product,
        user_organization: UserOrganization,
    ) -> None:
        # load
        product_organization_loaded = await product_service.get_loaded(
            session, product.id
        )
        assert product_organization_loaded

        update_schema = ProductUpdate(medias=[uuid.uuid4()])
        with pytest.raises(PolarRequestValidationError):
            await product_service.update(
                session,
                authz,
                product_organization_loaded,
                update_schema,
                auth_subject,
            )

    @pytest.mark.auth(
        AuthSubjectFixture(subject="user"),
        AuthSubjectFixture(subject="organization"),
    )
    @pytest.mark.parametrize(
        "file_kwargs",
        [
            {"service": FileServiceTypes.downloadable},
            {"is_enabled": False},
            {"is_uploaded": False},
        ],
    )
    async def test_invalid_media(
        self,
        file_kwargs: dict[str, Any],
        save_fixture: SaveFixture,
        auth_subject: AuthSubject[User],
        session: AsyncSession,
        authz: Authz,
        product: Product,
        organization: Organization,
        user_organization: UserOrganization,
    ) -> None:
        file = File(
            **{
                "organization": organization,
                "name": "Product Cover",
                "path": "/product-cover.jpg",
                "mime_type": "image/jpeg",
                "size": 1024,
                "service": FileServiceTypes.product_media,
                "is_enabled": True,
                "is_uploaded": True,
                **file_kwargs,
            }
        )
        await save_fixture(file)

        # load
        product_organization_loaded = await product_service.get_loaded(
            session, product.id
        )
        assert product_organization_loaded

        update_schema = ProductUpdate(medias=[file.id])
        with pytest.raises(PolarRequestValidationError):
            await product_service.update(
                session,
                authz,
                product_organization_loaded,
                update_schema,
                auth_subject,
            )

    @pytest.mark.auth(
        AuthSubjectFixture(subject="user"),
        AuthSubjectFixture(subject="organization"),
    )
    async def test_valid_media(
        self,
        save_fixture: SaveFixture,
        auth_subject: AuthSubject[User],
        session: AsyncSession,
        authz: Authz,
        product: Product,
        organization: Organization,
        user_organization: UserOrganization,
    ) -> None:
        file = File(
            **{
                "organization": organization,
                "name": "Product Cover",
                "path": "/product-cover.jpg",
                "mime_type": "image/jpeg",
                "size": 1024,
                "service": FileServiceTypes.product_media,
                "is_enabled": True,
                "is_uploaded": True,
            }
        )
        await save_fixture(file)

        # load
        product_organization_loaded = await product_service.get_loaded(
            session, product.id
        )
        assert product_organization_loaded

        update_schema = ProductUpdate(medias=[file.id])
        updated_product = await product_service.update(
            session,
            authz,
            product_organization_loaded,
            update_schema,
            auth_subject,
        )

        assert len(updated_product.medias) == 1


@pytest.mark.asyncio
@pytest.mark.skip_db_asserts
class TestUpdateBenefits:
    @pytest.mark.auth
    async def test_not_writable_product(
        self,
        auth_subject: AuthSubject[User],
        session: AsyncSession,
        authz: Authz,
        product: Product,
    ) -> None:
        with pytest.raises(NotPermitted):
            await product_service.update_benefits(
                session, authz, product, [], auth_subject
            )

    @pytest.mark.auth(
        AuthSubjectFixture(subject="user"),
        AuthSubjectFixture(subject="organization"),
    )
    async def test_not_existing_benefit(
        self,
        session: AsyncSession,
        save_fixture: SaveFixture,
        authz: Authz,
        auth_subject: AuthSubject[User | Organization],
        user_organization: UserOrganization,
        product: Product,
        benefits: list[Benefit],
    ) -> None:
        product = await set_product_benefits(
            save_fixture, product=product, benefits=benefits
        )
        assert len(product.product_benefits) == len(benefits)

        with pytest.raises(PolarRequestValidationError):
            await product_service.update_benefits(
                session,
                authz,
                product,
                [uuid.uuid4()],
                auth_subject,
            )

        assert len(product.product_benefits) == len(benefits)

    @pytest.mark.auth(
        AuthSubjectFixture(subject="user"),
        AuthSubjectFixture(subject="organization"),
    )
    async def test_added_benefits(
        self,
        save_fixture: SaveFixture,
        session: AsyncSession,
        enqueue_job_mock: AsyncMock,
        authz: Authz,
        auth_subject: AuthSubject[User | Organization],
        user_organization: UserOrganization,
        product: Product,
        benefits: list[Benefit],
    ) -> None:
        await set_product_benefits(save_fixture, product=product, benefits=[])

        (
            product,
            added,
            deleted,
        ) = await product_service.update_benefits(
            session,
            authz,
            product,
            [benefit.id for benefit in benefits],
            auth_subject,
        )
        await session.flush()

        assert len(product.product_benefits) == len(benefits)
        for i, product_benefit in enumerate(product.product_benefits):
            assert product_benefit.order == i
            assert benefits[i].id == product_benefit.benefit_id

        assert len(added) == len(benefits)
        assert len(deleted) == 0

        enqueue_job_mock.assert_has_calls(
            [
                call(
                    "subscription.subscription.update_product_benefits_grants",
                    product.id,
                ),
                call("order.update_product_benefits_grants", product.id),
            ]
        )

    @pytest.mark.auth(
        AuthSubjectFixture(subject="user"),
        AuthSubjectFixture(subject="organization"),
    )
    async def test_order(
        self,
        save_fixture: SaveFixture,
        session: AsyncSession,
        enqueue_job_mock: AsyncMock,
        authz: Authz,
        auth_subject: AuthSubject[User | Organization],
        user_organization: UserOrganization,
        product: Product,
        benefits: list[Benefit],
    ) -> None:
        await set_product_benefits(save_fixture, product=product, benefits=[])

        (
            product,
            added,
            deleted,
        ) = await product_service.update_benefits(
            session,
            authz,
            product,
            [benefit.id for benefit in benefits[::-1]],
            auth_subject,
        )
        await session.flush()

        assert len(product.product_benefits) == len(benefits)
        for i, product_benefit in enumerate(product.product_benefits):
            assert product_benefit.order == i
            assert benefits[-i - 1].id == product_benefit.benefit_id

        assert len(added) == len(benefits)
        assert len(deleted) == 0

        enqueue_job_mock.assert_has_calls(
            [
                call(
                    "subscription.subscription.update_product_benefits_grants",
                    product.id,
                ),
                call("order.update_product_benefits_grants", product.id),
            ]
        )

    @pytest.mark.auth(
        AuthSubjectFixture(subject="user"),
        AuthSubjectFixture(subject="organization"),
    )
    async def test_deleted(
        self,
        session: AsyncSession,
        save_fixture: SaveFixture,
        enqueue_job_mock: AsyncMock,
        authz: Authz,
        auth_subject: AuthSubject[User | Organization],
        user_organization: UserOrganization,
        product: Product,
        benefits: list[Benefit],
    ) -> None:
        product = await set_product_benefits(
            save_fixture,
            product=product,
            benefits=benefits,
        )

        (
            product,
            added,
            deleted,
        ) = await product_service.update_benefits(
            session, authz, product, [], auth_subject
        )
        await session.flush()

        assert len(product.product_benefits) == 0
        assert len(added) == 0
        assert len(deleted) == len(benefits)

        enqueue_job_mock.assert_has_calls(
            [
                call(
                    "subscription.subscription.update_product_benefits_grants",
                    product.id,
                ),
                call("order.update_product_benefits_grants", product.id),
            ]
        )

    @pytest.mark.auth(
        AuthSubjectFixture(subject="user"),
        AuthSubjectFixture(subject="organization"),
    )
    async def test_reordering(
        self,
        session: AsyncSession,
        save_fixture: SaveFixture,
        enqueue_job_mock: AsyncMock,
        authz: Authz,
        auth_subject: AuthSubject[User | Organization],
        user_organization: UserOrganization,
        product: Product,
        benefits: list[Benefit],
    ) -> None:
        product = await set_product_benefits(
            save_fixture,
            product=product,
            benefits=benefits,
        )

        (
            product,
            added,
            deleted,
        ) = await product_service.update_benefits(
            session,
            authz,
            product,
            [benefit.id for benefit in benefits[::-1]],
            auth_subject,
        )

        assert len(product.product_benefits) == len(benefits)
        for i, product_benefit in enumerate(product.product_benefits):
            assert product_benefit.order == i
            assert benefits[-i - 1].id == product_benefit.benefit_id

        assert len(added) == 0
        assert len(deleted) == 0

        enqueue_job_mock.assert_has_calls(
            [
                call(
                    "subscription.subscription.update_product_benefits_grants",
                    product.id,
                ),
                call("order.update_product_benefits_grants", product.id),
            ]
        )

    @pytest.mark.auth(
        AuthSubjectFixture(subject="user"),
        AuthSubjectFixture(subject="organization"),
    )
    async def test_add_not_selectable(
        self,
        session: AsyncSession,
        save_fixture: SaveFixture,
        authz: Authz,
        auth_subject: AuthSubject[User | Organization],
        user_organization: UserOrganization,
        organization: Organization,
        product: Product,
    ) -> None:
        not_selectable_benefit = await create_benefit(
            save_fixture,
            type=BenefitType.custom,
            is_tax_applicable=True,
            organization=organization,
            selectable=False,
            properties={"note": None},
        )

        with pytest.raises(PolarRequestValidationError):
            await product_service.update_benefits(
                session,
                authz,
                product,
                [not_selectable_benefit.id],
                auth_subject,
            )

    @pytest.mark.auth(
        AuthSubjectFixture(subject="user"),
        AuthSubjectFixture(subject="organization"),
    )
    async def test_remove_not_selectable(
        self,
        session: AsyncSession,
        save_fixture: SaveFixture,
        authz: Authz,
        auth_subject: AuthSubject[User | Organization],
        user_organization: UserOrganization,
        organization: Organization,
        product: Product,
    ) -> None:
        not_selectable_benefit = await create_benefit(
            save_fixture,
            type=BenefitType.custom,
            is_tax_applicable=True,
            organization=organization,
            selectable=False,
            properties={"note": None},
        )

        product = await set_product_benefits(
            save_fixture,
            product=product,
            benefits=[not_selectable_benefit],
        )

        with pytest.raises(PolarRequestValidationError):
            await product_service.update_benefits(
                session,
                authz,
                product,
                [],
                auth_subject,
            )

    @pytest.mark.auth(
        AuthSubjectFixture(subject="user"),
        AuthSubjectFixture(subject="organization"),
    )
    async def test_add_with_existing_not_selectable(
        self,
        session: AsyncSession,
        save_fixture: SaveFixture,
        enqueue_job_mock: AsyncMock,
        authz: Authz,
        auth_subject: AuthSubject[User | Organization],
        user_organization: UserOrganization,
        organization: Organization,
        product: Product,
    ) -> None:
        not_selectable_benefit = await create_benefit(
            save_fixture,
            type=BenefitType.custom,
            is_tax_applicable=True,
            organization=organization,
            selectable=False,
            properties={"note": None},
        )
        selectable_benefit = await create_benefit(
            save_fixture,
            type=BenefitType.custom,
            is_tax_applicable=True,
            organization=organization,
            description="SELECTABLE",
        )
        product = await set_product_benefits(
            save_fixture,
            product=product,
            benefits=[not_selectable_benefit],
        )

        (
            _,
            added,
            deleted,
        ) = await product_service.update_benefits(
            session,
            authz,
            product,
            [not_selectable_benefit.id, selectable_benefit.id],
            auth_subject,
        )
        assert len(added) == 1
        assert selectable_benefit.id in [a.id for a in added]
        assert len(deleted) == 0

        enqueue_job_mock.assert_has_calls(
            [
                call(
                    "subscription.subscription.update_product_benefits_grants",
                    product.id,
                ),
                call("order.update_product_benefits_grants", product.id),
            ]
        )
