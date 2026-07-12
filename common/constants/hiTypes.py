from __future__ import annotations

FHIR_BASE = "https://nrces.in/ndhm/fhir/r4/StructureDefinition"
SNOMED_SYSTEM = "http://snomed.info/sct"

DOCUMENT_BUNDLE_PROFILE = f"{FHIR_BASE}/DocumentBundle"
DOCUMENT_REFERENCE_PROFILE = f"{FHIR_BASE}/DocumentReference"

# Keys are the ABDM API hiType values (sent in link/carecontext and health-information requests).
# ABDM values differ from the NRCES FHIR StructureDefinition profile name suffix (e.g. OPConsultation → OPConsultRecord).

PDF_SUPPORTED_HI_TYPES: set[str] = {
    "HealthDocumentRecord",
    "OPConsultation",
    "DiagnosticReport",
    "DischargeSummary",
    "Prescription",
    "ImmunizationRecord",
    "WellnessRecord",
}

COMPOSITION_PROFILE_BY_HI_TYPE: dict[str, str] = {
    "HealthDocumentRecord": f"{FHIR_BASE}/HealthDocumentRecord",
    "OPConsultation": f"{FHIR_BASE}/OPConsultRecord",
    "DiagnosticReport": f"{FHIR_BASE}/DiagnosticReportRecord",
    "DischargeSummary": f"{FHIR_BASE}/DischargeSummaryRecord",
    "Prescription": f"{FHIR_BASE}/PrescriptionRecord",
    "ImmunizationRecord": f"{FHIR_BASE}/ImmunizationRecord",
    "WellnessRecord": f"{FHIR_BASE}/WellnessRecord",
    "Invoice": f"{FHIR_BASE}/InvoiceRecord",
}

# SNOMED-CT code (code, display) per HI type — used in Composition.type and section.code
SNOMED_CODE_BY_HI_TYPE: dict[str, tuple[str, str]] = {
    "OPConsultation": ("371530004", "Clinical consultation report"),
    "DiagnosticReport": ("4321000179101", "Diagnostic report"),
    "DischargeSummary": ("373942005", "Discharge summary"),
    "Prescription": ("440545006", "Prescription"),
    "ImmunizationRecord": ("41000179103", "Immunization record"),
    "WellnessRecord": ("371529009", "Health maintenance report"),
    "HealthDocumentRecord": ("419891008", "Record artifact"),
    "Invoice": ("419891008", "Record artifact"),
}

SNOMED_CODE_DEFAULT: tuple[str, str] = ("371530004", "Clinical consultation report")
