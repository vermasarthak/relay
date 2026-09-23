import os
from relay.db.session import SessionLocal, Base, engine
from relay.models.entities import Tenant, User, Membership, UserRole, CustomerAccount, Document, DocumentVersion
from relay.core.security import hash_password

def seed_database():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Check if already seeded
        if db.query(Tenant).first():
            print("Database already seeded.")
            return

        print("Seeding multi-tenant test data...")

        # 1. Tenants
        tenant_a = Tenant(id="ten_acme_corp", name="Acme Cloud Services", slug="acme")
        tenant_b = Tenant(id="ten_globex_ai", name="Globex Intelligence", slug="globex")
        db.add_all([tenant_a, tenant_b])
        db.flush()

        # 2. Users
        admin_user = User(
            id="usr_alice_admin",
            email="alice@acme.com",
            full_name="Alice Admin",
            hashed_password=hash_password("admin123456")
        )
        bob_reviewer = User(
            id="usr_bob_reviewer",
            email="bob@acme.com",
            full_name="Bob Reviewer",
            hashed_password=hash_password("reviewer123456")
        )
        globex_user = User(
            id="usr_carol_globex",
            email="carol@globex.com",
            full_name="Carol Globex",
            hashed_password=hash_password("globex123456")
        )
        db.add_all([admin_user, bob_reviewer, globex_user])
        db.flush()

        # 3. Memberships
        db.add_all([
            Membership(tenant_id=tenant_a.id, user_id=admin_user.id, role=UserRole.ADMIN),
            Membership(tenant_id=tenant_a.id, user_id=bob_reviewer.id, role=UserRole.REVIEWER),
            Membership(tenant_id=tenant_b.id, user_id=globex_user.id, role=UserRole.ADMIN)
        ])

        # 4. Customer Accounts for Acme
        acc1 = CustomerAccount(
            tenant_id=tenant_a.id,
            customer_email="john@customer.com",
            customer_name="John Doe",
            plan_tier="pro_monthly",
            subscription_status="active",
            monthly_rate_cents=2900,
            days_since_billing=4
        )
        acc2 = CustomerAccount(
            tenant_id=tenant_a.id,
            customer_email="sarah@customer.com",
            customer_name="Sarah Smith",
            plan_tier="enterprise_annual",
            subscription_status="active",
            monthly_rate_cents=9900,
            days_since_billing=28 # outside 14-day refund window
        )
        db.add_all([acc1, acc2])

        # 5. Policy Documents for Acme
        doc_refund = Document(
            tenant_id=tenant_a.id,
            title="Refund Policy & Eligibility",
            category="policy",
            current_version=1
        )
        db.add(doc_refund)
        db.flush()

        ver_refund = DocumentVersion(
            document_id=doc_refund.id,
            version=1,
            content=(
                "Acme Cloud Services Refund Policy (v1.0):\n\n"
                "1. Subscriptions may be refunded within 14 days of the latest billing date upon explicit customer request.\n"
                "2. Standard monthly plans ($29) are eligible for full automatic refund within the 14-day window.\n"
                "3. Requests beyond 14 days are ineligible and require managerial abstention.\n"
                "4. All approved refunds are executed via the local sandbox payment ledger with strict idempotency."
            ),
            summary="14-day refund window policy for monthly plans."
        )

        doc_cancel = Document(
            tenant_id=tenant_a.id,
            title="Subscription Cancellation Guidelines",
            category="policy",
            current_version=1
        )
        db.add(doc_cancel)
        db.flush()

        ver_cancel = DocumentVersion(
            document_id=doc_cancel.id,
            version=1,
            content=(
                "Acme Cloud Services Cancellation Policy (v1.0):\n\n"
                "1. Customers may cancel their active recurring subscription at any time.\n"
                "2. Cancellation takes effect immediately in the billing sandbox upon supervisor approval.\n"
                "3. Account remains active until the end of the billing period unless immediate termination is specified."
            ),
            summary="Immediate cancellation guidelines."
        )
        db.add_all([ver_refund, ver_cancel])

        db.commit()
        print("Database seeding completed successfully.")

    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
