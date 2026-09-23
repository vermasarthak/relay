import re

from sqlalchemy.orm import Session

from relay.models.entities import CustomerAccount, Document, DocumentVersion, EvidenceReference


class EvidenceRetriever:
    def __init__(self, db: Session, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    def retrieve_for_ticket(self, ticket_id: str, customer_email: str, text: str) -> list[EvidenceReference]:
        # Purge stale evidence items for this ticket if re-analyzing
        self.db.query(EvidenceReference).filter(
            EvidenceReference.tenant_id == self.tenant_id,
            EvidenceReference.ticket_id == ticket_id
        ).delete(synchronize_session=False)

        evidence_items: list[EvidenceReference] = []

        # 1. Lookup Customer Account state
        account = self.db.query(CustomerAccount).filter(
            CustomerAccount.tenant_id == self.tenant_id,
            CustomerAccount.customer_email == customer_email
        ).first()

        if account:
            acc_excerpt = (
                f"Customer Account Info: Plan={account.plan_tier}, "
                f"SubscriptionStatus={account.subscription_status}, "
                f"MonthlyRateCents={account.monthly_rate_cents}, "
                f"DaysSinceBillingCycle={account.days_since_billing}"
            )
            evi_acc = EvidenceReference(
                tenant_id=self.tenant_id,
                ticket_id=ticket_id,
                source_type="customer_account",
                source_id=account.id,
                source_title=f"Account Details ({account.customer_email})",
                excerpt=acc_excerpt,
                relevance_score=1.0
            )
            self.db.add(evi_acc)
            evidence_items.append(evi_acc)

        # 2. Policy retrieval using keyword/full-text matching across latest DocumentVersions
        docs = self.db.query(Document).filter(Document.tenant_id == self.tenant_id).all()
        keywords = set(re.findall(r'\b\w{3,}\b', text.lower()))

        for doc in docs:
            latest_version = self.db.query(DocumentVersion).filter(
                DocumentVersion.document_id == doc.id,
                DocumentVersion.version == doc.current_version
            ).first()

            if not latest_version:
                continue

            content_lower = latest_version.content.lower()
            matching_keywords = [kw for kw in keywords if kw in content_lower]
            
            # Simple relevance scoring based on matched terms
            if matching_keywords or "policy" in doc.category.lower():
                score = len(matching_keywords) / (len(keywords) + 1e-5)
                # Take the most relevant paragraphs or full text if concise
                paragraphs = [p.strip() for p in latest_version.content.split("\n\n") if p.strip()]
                best_para = paragraphs[0] if paragraphs else latest_version.content
                for p in paragraphs:
                    if any(kw in p.lower() for kw in matching_keywords):
                        best_para = p
                        break

                evi_doc = EvidenceReference(
                    tenant_id=self.tenant_id,
                    ticket_id=ticket_id,
                    source_type="policy_doc",
                    source_id=latest_version.id,
                    source_title=f"{doc.title} (v{doc.current_version})",
                    excerpt=best_para,
                    relevance_score=min(1.0, max(0.4, float(score)))
                )
                self.db.add(evi_doc)
                evidence_items.append(evi_doc)

        self.db.flush()
        return evidence_items
