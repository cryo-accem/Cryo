from decimal import Decimal


GST_RATE = Decimal("0.18")
FREEZING_RATE = Decimal("125")
CLIPPING_RATE = Decimal("125")
PROCESSING_RATE = Decimal("20000")

SLOT_RATES = {
    "internal": Decimal("3000"),
    "academic": Decimal("12000"),
    "industrial": Decimal("50000"),
}


def pricing_category(origin):
    normalized = (origin or "").strip().casefold()
    if normalized == "internal":
        return "internal"
    if normalized in {"external", "academic"}:
        return "academic"
    if normalized in {"industry", "industrial"}:
        return "industrial"
    raise ValueError("Unsupported booking origin.")


def calculate_booking_revenue(booking, actual_slots, actual_grids, processing_requested=False):
    category = pricing_category(booking["origin"])
    actual_slots = Decimal(str(actual_slots))
    actual_grids = Decimal(str(actual_grids))

    slot_charge = SLOT_RATES[category] * actual_slots
    freezing_charge = FREEZING_RATE * actual_grids
    clipping_charge = CLIPPING_RATE * actual_grids
    processing_charge = PROCESSING_RATE if processing_requested and category != "internal" else Decimal("0")
    subtotal = slot_charge + freezing_charge + clipping_charge + processing_charge
    gst = (slot_charge + processing_charge) * GST_RATE if category != "internal" else Decimal("0")

    return {
        "actual_slots": actual_slots,
        "actual_grids": actual_grids,
        "slot_charge": slot_charge,
        "freezing_charge": freezing_charge,
        "clipping_charge": clipping_charge,
        "processing_charge": processing_charge,
        "subtotal": subtotal,
        "gst": gst,
        "total_billed": subtotal + gst,
        "category": category,
    }
