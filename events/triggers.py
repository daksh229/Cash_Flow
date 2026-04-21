"""
Event Name Catalogue
====================
Single place to enumerate every event emitted in the system. Using this
class keeps publisher/subscriber names in sync and makes grep-ability
trivial. Add new events here before emitting them.

The S1/S2 re-scoring events exist because the SSD requires AR/AP
predictions to update when upstream records change, rather than only
on the next batch run.
"""


class EventName:
    INVOICE_CREATED     = "invoice.created"
    INVOICE_PAID        = "invoice.paid"
    INVOICE_UPDATED     = "invoice.updated"

    BILL_CREATED        = "bill.created"
    BILL_PAID           = "bill.paid"
    BILL_UPDATED        = "bill.updated"

    CUSTOMER_UPDATED    = "customer.updated"
    VENDOR_UPDATED      = "vendor.updated"

    FEATURE_REFRESHED   = "feature_store.refreshed"
    FORECAST_PUBLISHED  = "forecast.published"

    @classmethod
    def all(cls):
        return [v for k, v in vars(cls).items()
                if not k.startswith("_") and isinstance(v, str)]
