"""Processors - 格式提取器"""

from .base import BaseProcessor
from .cn_sections import CNSectionsProcessor
from .hk_sections import HKSectionsProcessor
from .us_10k_sections import US10KSectionsProcessor
from .us_10q_sections import US10QSectionsProcessor
from .us_20f_sections import US20FSectionsProcessor
from .us_8k_sections import US8KSectionsProcessor
from .table_extractor import FinancialTableExtractor
from .section_identifier import SectionIdentifier

__all__ = [
    "BaseProcessor",
    "CNSectionsProcessor",
    "HKSectionsProcessor",
    "US10KSectionsProcessor",
    "US10QSectionsProcessor",
    "US20FSectionsProcessor",
    "US8KSectionsProcessor",
    "FinancialTableExtractor",
    "SectionIdentifier",
]
