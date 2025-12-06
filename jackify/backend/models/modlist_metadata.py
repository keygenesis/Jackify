"""
Data models for modlist metadata from jackify-engine JSON output.

These models match the JSON schema documented in MODLIST_METADATA_IMPLEMENTATION.md
"""
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


@dataclass
class ModlistImages:
    """Image URLs for modlist (small thumbnail and large banner)"""
    small: str
    large: str


@dataclass
class ModlistLinks:
    """External links associated with the modlist"""
    image: Optional[str] = None
    readme: Optional[str] = None
    download: Optional[str] = None
    discordURL: Optional[str] = None
    websiteURL: Optional[str] = None


@dataclass
class ModlistSizes:
    """Size information for modlist downloads and installation"""
    downloadSize: int
    downloadSizeFormatted: str
    installSize: int
    installSizeFormatted: str
    totalSize: int
    totalSizeFormatted: str
    numberOfArchives: int
    numberOfInstalledFiles: int


@dataclass
class ModlistValidation:
    """Validation status from Wabbajack build server (optional)"""
    failed: int = 0
    passed: int = 0
    updating: int = 0
    mirrored: int = 0
    modListIsMissing: bool = False
    hasFailures: bool = False


@dataclass
class ModlistMetadata:
    """Complete modlist metadata from jackify-engine"""
    # Basic information
    title: str
    description: str
    author: str
    maintainers: List[str]
    namespacedName: str
    repositoryName: str
    machineURL: str

    # Game information
    game: str
    gameHumanFriendly: str

    # Status flags
    official: bool
    nsfw: bool
    utilityList: bool
    forceDown: bool
    imageContainsTitle: bool

    # Version information
    version: Optional[str] = None
    displayVersionOnlyInInstallerView: bool = False

    # Dates
    dateCreated: Optional[str] = None  # ISO8601 format
    dateUpdated: Optional[str] = None  # ISO8601 format

    # Categorization
    tags: List[str] = field(default_factory=list)

    # Nested objects
    links: Optional[ModlistLinks] = None
    sizes: Optional[ModlistSizes] = None
    images: Optional[ModlistImages] = None

    # Optional data (only if flags specified)
    validation: Optional[ModlistValidation] = None
    mods: List[str] = field(default_factory=list)

    def is_available(self) -> bool:
        """Check if modlist is available for installation"""
        if self.forceDown:
            return False
        if self.validation and self.validation.hasFailures:
            return False
        return True

    def is_broken(self) -> bool:
        """Check if modlist has validation failures"""
        return self.validation.hasFailures if self.validation else False

    def get_date_updated_datetime(self) -> Optional[datetime]:
        """Parse dateUpdated string to datetime object"""
        if not self.dateUpdated:
            return None
        try:
            return datetime.fromisoformat(self.dateUpdated.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return None

    def get_date_created_datetime(self) -> Optional[datetime]:
        """Parse dateCreated string to datetime object"""
        if not self.dateCreated:
            return None
        try:
            return datetime.fromisoformat(self.dateCreated.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return None


@dataclass
class ModlistMetadataResponse:
    """Root response object from jackify-engine list-modlists --json"""
    metadataVersion: str
    timestamp: str  # ISO8601 format
    count: int
    modlists: List[ModlistMetadata]

    def get_timestamp_datetime(self) -> Optional[datetime]:
        """Parse timestamp string to datetime object"""
        try:
            return datetime.fromisoformat(self.timestamp.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return None

    def filter_by_game(self, game: str) -> List[ModlistMetadata]:
        """Filter modlists by game name"""
        return [m for m in self.modlists if m.game.lower() == game.lower()]

    def filter_available_only(self) -> List[ModlistMetadata]:
        """Filter to only available (non-broken, non-forced-down) modlists"""
        return [m for m in self.modlists if m.is_available()]

    def filter_by_tag(self, tag: str) -> List[ModlistMetadata]:
        """Filter modlists by tag"""
        return [m for m in self.modlists if tag.lower() in [t.lower() for t in m.tags]]

    def filter_official_only(self) -> List[ModlistMetadata]:
        """Filter to only official modlists"""
        return [m for m in self.modlists if m.official]

    def search(self, query: str) -> List[ModlistMetadata]:
        """Search modlists by title, description, or author"""
        query_lower = query.lower()
        return [
            m for m in self.modlists
            if query_lower in m.title.lower()
            or query_lower in m.description.lower()
            or query_lower in m.author.lower()
        ]


def parse_modlist_metadata_from_dict(data: dict) -> ModlistMetadata:
    """Parse a modlist metadata dictionary into ModlistMetadata object"""
    # Parse nested objects
    images = ModlistImages(**data['images']) if 'images' in data and data['images'] else None
    links = ModlistLinks(**data['links']) if 'links' in data and data['links'] else None
    sizes = ModlistSizes(**data['sizes']) if 'sizes' in data and data['sizes'] else None
    validation = ModlistValidation(**data['validation']) if 'validation' in data and data['validation'] else None

    # Create ModlistMetadata with nested objects
    metadata = ModlistMetadata(
        title=data['title'],
        description=data['description'],
        author=data['author'],
        maintainers=data.get('maintainers', []),
        namespacedName=data['namespacedName'],
        repositoryName=data['repositoryName'],
        machineURL=data['machineURL'],
        game=data['game'],
        gameHumanFriendly=data['gameHumanFriendly'],
        official=data['official'],
        nsfw=data['nsfw'],
        utilityList=data['utilityList'],
        forceDown=data['forceDown'],
        imageContainsTitle=data['imageContainsTitle'],
        version=data.get('version'),
        displayVersionOnlyInInstallerView=data.get('displayVersionOnlyInInstallerView', False),
        dateCreated=data.get('dateCreated'),
        dateUpdated=data.get('dateUpdated'),
        tags=data.get('tags', []),
        links=links,
        sizes=sizes,
        images=images,
        validation=validation,
        mods=data.get('mods', [])
    )

    return metadata


def parse_modlist_metadata_response(data: dict) -> ModlistMetadataResponse:
    """Parse the full JSON response from jackify-engine into ModlistMetadataResponse"""
    modlists = [parse_modlist_metadata_from_dict(m) for m in data.get('modlists', [])]

    return ModlistMetadataResponse(
        metadataVersion=data['metadataVersion'],
        timestamp=data['timestamp'],
        count=data['count'],
        modlists=modlists
    )
