import re

from django.db.models import ExpressionWrapper
from django.db.models import F
from django.db.models import IntegerField
from django.db.models import OuterRef
from django.db.models import Q
from django.db.models import Subquery
from django.db.models import Value
from django_filters.rest_framework import BooleanFilter
from django_filters.rest_framework import CharFilter
from le_utils.constants import content_kinds
from le_utils.constants import roles
from rest_framework.permissions import IsAuthenticated

from contentcuration.models import Channel
from contentcuration.models import ContentNode
from contentcuration.models import File
from contentcuration.utils.pagination import CachedListPagination
from contentcuration.viewsets.base import RequiredFilterSet
from contentcuration.viewsets.base import ValuesViewset
from contentcuration.viewsets.common import NotNullMapArrayAgg
from contentcuration.viewsets.common import UUIDFilter
from contentcuration.viewsets.common import UUIDInFilter
from contentcuration.viewsets.contentnode import get_title


class ListPagination(CachedListPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


uuid_re = re.compile("([a-f0-9]{32})")


class ContentNodeFilter(RequiredFilterSet):
    keywords = CharFilter(method="filter_keywords")
    languages = CharFilter(method="filter_languages")
    licenses = CharFilter(method="filter_licenses")
    kinds = CharFilter(method="filter_kinds")
    coach = BooleanFilter(method="filter_coach")
    author = CharFilter(method="filter_author")
    resources = BooleanFilter(method="filter_resources")
    assessments = BooleanFilter(method="filter_assessments")
    created_after = CharFilter(method="filter_created_after")
    channel_id__in = UUIDInFilter(field_name="channel_id")
    channel_list = CharFilter(method="filter_channel_list")
    exclude_channel = UUIDFilter(field_name="channel_id", exclude=True)

    def filter_channel_list(self, queryset, name, value):
        user = not self.request.user.is_anonymous and self.request.user
        channel_ids = []
        if value == "public":
            channel_ids = Channel.objects.filter(public=True, deleted=False).values_list("id", flat=True)
        elif value == "edit" and user:
            channel_ids = user.editable_channels.values_list("id", flat=True)
        elif value == "bookmark" and user:
            channel_ids = user.bookmarked_channels.values_list("id", flat=True)
        elif value == "view" and user:
            channel_ids = user.view_only_channels.values_list("id", flat=True)
        return queryset.filter(channel_id__in=list(channel_ids))

    def filter_keywords(self, queryset, name, value):
        filter_query = Q(title__icontains=value) | Q(description__icontains=value)

        tags_node_ids = ContentNode.tags.through.objects.filter(
            contenttag__tag_name__icontains=value
        ).values_list("contentnode_id", flat=True)

        # Check if we have a Kolibri node id or ids and add them to the search if so.
        # Add to, rather than replace, the filters so that we never misinterpret a search term as a UUID.
        # node_ids = uuid_re.findall(value) + list(tags_node_ids)
        node_ids = uuid_re.findall(value)
        for node_id in node_ids:
            # check for the major ID types
            filter_query |= Q(node_id=node_id)
            filter_query |= Q(content_id=node_id)
            filter_query |= Q(id=node_id)

        return queryset.filter(Q(id__in=list(tags_node_ids)) | filter_query)

    def filter_author(self, queryset, name, value):
        return queryset.filter(
            Q(author__icontains=value)
            | Q(aggregator__icontains=value)
            | Q(provider__icontains=value)
        )

    def filter_languages(self, queryset, name, value):
        return queryset.filter(language__lang_code__in=value.split(","))

    def filter_licenses(self, queryset, name, value):
        licenses = [int(li) for li in value.split(",")]
        return queryset.filter(license__in=licenses)

    def filter_kinds(self, queryset, name, value):
        return queryset.filter(kind_id__in=value.split(","))

    def filter_coach(self, queryset, name, value):
        return queryset.filter(role_visibility=roles.COACH)

    def filter_resources(self, queryset, name, value):
        return queryset.exclude(kind_id=content_kinds.TOPIC)

    def filter_assessments(self, queryset, name, value):
        return queryset.filter(kind_id=content_kinds.EXERCISE)

    def filter_created_after(self, queryset, name, value):
        date = re.search(r"(\d{4})-0?(\d+)-(\d+)", value)
        return queryset.filter(
            created__year__gte=date.group(1),
            created__month__gte=date.group(2),
            created__day__gte=date.group(3),
        )

    class Meta:
        model = ContentNode
        fields = (
            "keywords",
            "languages",
            "licenses",
            "kinds",
            "coach",
            "author",
            "resources",
            "assessments",
        )


class SearchContentNodeViewSet(ValuesViewset):
    queryset = ContentNode.objects.all()
    filterset_class = ContentNodeFilter
    pagination_class = ListPagination
    permission_classes = [IsAuthenticated]

    values = (
        "id",
        "content_id",
        "node_id",
        "title",
        "description",
        "author",
        "provider",
        "kind__kind",
        "channel_id",
        "resource_count",
        "thumbnail_checksum",
        "thumbnail_extension",
        "thumbnail_encoding",
        "published",
        "modified",
        "parent_id",
        "changed",
        "content_tags",
        "original_channel_name",
    )

    field_map = {
        "title": get_title,
    }

    def get_queryset(self):
        queryset = super(SearchContentNodeViewSet, self).get_queryset()
        return ContentNode._annotate_channel_id(queryset)

    def annotate_queryset(self, queryset):
        """
        1. Do a distinct by 'content_id,' using the original node if possible
        2. Annotate lists of content node and channel pks
        """
        thumbnails = File.objects.filter(
            contentnode=OuterRef("id"), preset__thumbnail=True
        )

        descendant_resources_count = ExpressionWrapper(((F("rght") - F("lft") - Value(1)) / Value(2)), output_field=IntegerField())

        channel_name = Subquery(
            Channel.objects.filter(pk=OuterRef("channel_id")).values(
                "name"
            )[:1]
        )

        queryset = queryset.annotate(
            resource_count=descendant_resources_count,
            thumbnail_checksum=Subquery(thumbnails.values("checksum")[:1]),
            thumbnail_extension=Subquery(
                thumbnails.values("file_format__extension")[:1]
            ),
            content_tags=NotNullMapArrayAgg("tags__tag_name"),
            original_channel_name=channel_name,
        )

        return queryset
