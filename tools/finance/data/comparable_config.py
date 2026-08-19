"""
可比公司配置（白名单+黑名单+行业分类自动过滤）

功能：
1. 白名单管理
2. 黑名单管理
3. 行业分类自动过滤
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class IndustryClassification(Enum):
    """行业分类"""
    READING = "reading"  # 阅读
    FILM_TV = "film_tv"  # 影视
    CONTENT_PLATFORM = "content_platform"  # 内容平台
    GAMING = "gaming"  # 游戏
    SOCIAL_MEDIA = "social_media"  # 社交媒体


@dataclass
class CompanyProfile:
    """公司画像"""
    name: str
    ticker: str
    market: str
    industry: IndustryClassification
    sub_industry: str


class ComparableConfig:
    """可比公司配置"""
    
    # 公司画像库
    COMPANY_PROFILES: Dict[str, CompanyProfile] = {
        "掌阅科技": CompanyProfile(
            name="掌阅科技",
            ticker="603533.SH",
            market="A股",
            industry=IndustryClassification.READING,
            sub_industry="数字阅读",
        ),
        "中文在线": CompanyProfile(
            name="中文在线",
            ticker="300364.SZ",
            market="A股",
            industry=IndustryClassification.READING,
            sub_industry="数字阅读",
        ),
        "阅文集团": CompanyProfile(
            name="阅文集团",
            ticker="00772.HK",
            market="港股",
            industry=IndustryClassification.READING,
            sub_industry="数字阅读",
        ),
        "B站": CompanyProfile(
            name="B站",
            ticker="09626.HK",
            market="港股",
            industry=IndustryClassification.CONTENT_PLATFORM,
            sub_industry="视频平台",
        ),
        "爱奇艺": CompanyProfile(
            name="爱奇艺",
            ticker="IQ.OQ",
            market="美股",
            industry=IndustryClassification.CONTENT_PLATFORM,
            sub_industry="视频平台",
        ),
        "迪士尼": CompanyProfile(
            name="迪士尼",
            ticker="DIS.N",
            market="美股",
            industry=IndustryClassification.FILM_TV,
            sub_industry="影视娱乐",
        ),
    }
    
    # 可比公司白名单
    COMPARABLE_WHITELIST: Dict[str, List[str]] = {
        "阅读": ["掌阅科技", "中文在线", "阅文集团"],
        "影视": ["华策影视", "光线传媒", "迪士尼"],
        "内容平台": ["B站", "爱奇艺"],
    }
    
    # 可比公司黑名单
    COMPARABLE_BLACKLIST: Dict[str, List[str]] = {
        "阅读": ["B站", "爱奇艺", "抖音", "Meta", "拼多多", "美团"],
    }
    
    @classmethod
    def get_comparable_companies(cls, industry: str, market: str = None) -> List[str]:
        """获取可比公司"""
        companies = cls.COMPARABLE_WHITELIST.get(industry, [])
        
        if market:
            # 按市场过滤
            filtered = []
            for company in companies:
                profile = cls.COMPANY_PROFILES.get(company)
                if profile and profile.market == market:
                    filtered.append(company)
            return filtered
        
        return companies
    
    @classmethod
    def is_comparable(cls, industry: str, company: str) -> bool:
        """检查是否为可比公司"""
        whitelist = cls.COMPARABLE_WHITELIST.get(industry, [])
        blacklist = cls.COMPARABLE_BLACKLIST.get(industry, [])
        
        if company in blacklist:
            return False
        
        if company in whitelist:
            return True
        
        return False
    
    @classmethod
    def filter_by_industry(cls, industry: IndustryClassification, 
                          companies: List[str]) -> List[str]:
        """按行业过滤可比公司"""
        filtered = []
        
        for company in companies:
            profile = cls.COMPANY_PROFILES.get(company)
            if profile and profile.industry == industry:
                filtered.append(company)
            else:
                logger.info(f"过滤非同业公司: {company}")
        
        return filtered
    
    @classmethod
    def validate_comparable(cls, industry: str, companies: List[str]) -> List[str]:
        """验证可比公司"""
        errors = []
        
        for company in companies:
            if not cls.is_comparable(industry, company):
                errors.append(f"{company}不是{industry}行业的可比公司")
        
        return errors
    
    @classmethod
    def get_company_profile(cls, company: str) -> Optional[CompanyProfile]:
        """获取公司画像"""
        return cls.COMPANY_PROFILES.get(company)
    
    @classmethod
    def add_company_profile(cls, profile: CompanyProfile):
        """添加公司画像"""
        cls.COMPANY_PROFILES[profile.name] = profile
    
    @classmethod
    def add_to_whitelist(cls, industry: str, company: str):
        """添加到白名单"""
        if industry not in cls.COMPARABLE_WHITELIST:
            cls.COMPARABLE_WHITELIST[industry] = []
        
        if company not in cls.COMPARABLE_WHITELIST[industry]:
            cls.COMPARABLE_WHITELIST[industry].append(company)
    
    @classmethod
    def add_to_blacklist(cls, industry: str, company: str):
        """添加到黑名单"""
        if industry not in cls.COMPARABLE_BLACKLIST:
            cls.COMPARABLE_BLACKLIST[industry] = []
        
        if company not in cls.COMPARABLE_BLACKLIST[industry]:
            cls.COMPARABLE_BLACKLIST[industry].append(company)
