"""Processors - 格式提取器"""

from .base import BaseProcessor
from .cn_sections import CNSectionsProcessor
from .hk_sections import HKSectionsProcessor
from .section_identifier import SectionIdentifier
from .table_extractor import FinancialTableExtractor
from .us_8k_sections import US8KSectionsProcessor
from .us_10k_sections import US10KSectionsProcessor
from .us_10q_sections import US10QSectionsProcessor
from .us_20f_sections import US20FSectionsProcessor

__all__ = [
    "BaseProcessor",
    "CNSectionsProcessor",
    "FinancialTableExtractor",
    "HKSectionsProcessor",
    "SectionIdentifier",
    "US8KSectionsProcessor",
    "US10KSectionsProcessor",
    "US10QSectionsProcessor",
    "US20FSectionsProcessor",
]
