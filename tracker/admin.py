from django.contrib import admin
from .models import Match, Referee, MatchReferee, ScrapeLog


class MatchRefereeInline(admin.TabularInline):
    model = MatchReferee
    extra = 1


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ('league', 'match_date', 'home_team', 'away_team', 'score', 'venue', 'week')
    list_filter = ('league', 'season')
    search_fields = ('home_team', 'away_team', 'venue')
    ordering = ('league', 'match_date')
    inlines = [MatchRefereeInline]


@admin.register(Referee)
class RefereeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(ScrapeLog)
class ScrapeLogAdmin(admin.ModelAdmin):
    list_display = ('league', 'scraped_at', 'success', 'matches_found', 'message')
    list_filter = ('league', 'success')
    readonly_fields = ('scraped_at',)
