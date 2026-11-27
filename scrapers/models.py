from datetime import datetime, timezone
from typing import Literal
from decimal import Decimal

import pycountry

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator
)


OpportunityType = Literal[
    "job",
    "internship",
    "graduate_program",
    "training",
    "scholarship",
    "competition",
    "hackathon",
    "freelance",
    "volunteering",
    "event"
]

SourceName = Literal[
    "wuzzuf",
    "forasna",
    "egyincs",
    "itida",
    "nti",
    "bayt",
    "devpost",
    "un_volunteers"
]

WorkMode = Literal[
    "on_site",
    "remote",
    "hybrid",
    "unknown"
]

EmploymentType = Literal[
    "full_time",
    "part_time",
    "contract",
    "temporary",
    "freelance",
    "unknown"
]

ExperienceLevel = Literal[
    "entry_level",
    "junior",
    "mid_level",
    "senior",
    "lead",
    "manager",
    "executive",
    "unknown"
]

OpportunityStatus = Literal[
    "active",
    "expired",
    "closed",
    "unknown"
]

DatePrecision = Literal[
    "exact",
    "date_only",
    "relative",
    "unknown"
]

SalaryPeriod = Literal[
    "hourly",
    "daily",
    "weekly",
    "monthly",
    "yearly",
    "project",
    "unknown"
]

class Opportunity(BaseModel):
    
    model_config = ConfigDict(extra="forbid")

    # Source identity

    source_name: SourceName
    source_opportunity_id: str | None = None
    source_url: HttpUrl

    # Opportunity information

    title: str = Field(min_length=1)
    organization: str | None = None
    description: str | None = None
    opportunity_type: OpportunityType
    location: str | None = None

    work_modes: list[WorkMode] | None = None
    employment_types: list[EmploymentType] | None = None
    categories: list[str] | None = None

    # Qualifications

    experience_level: ExperienceLevel | None = None
    experience_level_raw: str | None = None

    experience_years_min: Decimal | None = Field(
        default=None, ge=0
    )

    experience_years_max: Decimal | None = Field(
        default=None, ge=0
    )

    education_level: str | None = None
    required_skills: list[str] | None = None
    requirements: str | None = None

    # Financial information

    salary_min: Decimal | None = Field(
        default=None, ge=0
    )

    salary_max: Decimal | None = Field(
        default=None, ge=0
    )

    currency: str | None = None
    salary_period: SalaryPeriod | None = None

    # Dates

    published_at: datetime | None = None
    published_at_raw: str | None = None
    published_at_precision: DatePrecision | None = None

    deadline: datetime | None = None
    deadline_raw: str | None = None
    deadline_precision: DatePrecision | None = None

    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # Metadata

    status: OpportunityStatus = "unknown"
    source_status_raw: str | None = None
    raw_payload: dict

    # Validators

    @field_validator("organization")
    @classmethod
    def clean_organization(cls, value):

        if value is None:
            return None

        return " ".join(value.split()) or None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value):

        value = value.strip()

        if not value:
            raise ValueError("Title cannot be empty")

        return value

    @field_validator(
        "work_modes",
        "employment_types"
    )
    @classmethod
    def validate_standardized_arrays(cls, values):

        if values is None:
            return None

        values = list(dict.fromkeys(values))

        if "unknown" in values and len(values) > 1:
            raise ValueError(
                "Unknown cannot be combined with known values"
            )

        return values

    @field_validator(
        "required_skills",
        "categories"
    )
    @classmethod
    def clean_text_arrays(cls, values):

        if values is None:
            return None

        cleaned = []
        seen = set()

        for value in values:

            value = value.strip()
            normalized = value.casefold()

            if value and normalized not in seen:
                cleaned.append(value)
                seen.add(normalized)

        if values and not cleaned:
            return None

        return cleaned

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value):

        if value is None:
            return None

        value = value.strip().upper()

        if pycountry.currencies.get(alpha_3=value) is None:
            raise ValueError("Invalid ISO 4217 currency code")

        return value

    @field_validator(
        "published_at",
        "deadline",
        "collected_at"
    )
    @classmethod
    def validate_timestamps(cls, value):

        if value is None:
            return None

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamp must be timezone-aware")

        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_ranges(self):

        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_min > self.salary_max
        ):
            raise ValueError(
                "Minimum salary cannot exceed maximum salary"
            )

        if (
            self.experience_years_min is not None
            and self.experience_years_max is not None
            and self.experience_years_min
            > self.experience_years_max
        ):
            raise ValueError(
                "Minimum experience cannot exceed maximum experience"
            )

        return self

    @model_validator(mode="after")
    def validate_date_precision(self):

        for field in ("published_at", "deadline"):

            value = getattr(self, field)
            raw = getattr(self, f"{field}_raw")
            precision = getattr(self, f"{field}_precision")

            if value is not None and precision is None:
                raise ValueError(
                    f"{field} requires date precision"
                )

            if precision == "exact" and value is None:
                raise ValueError(
                    f"{field} requires an exact timestamp"
                )

            if precision in ("relative", "date_only") and not raw:
                raise ValueError(
                    f"{field} requires its original date value"
                )

        return self