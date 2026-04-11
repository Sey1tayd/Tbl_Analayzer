from django.db import models


LEAGUE_CHOICES = [
    ('BSL', 'Basketbol Süper Ligi (Erkekler)'),
    ('KBSL', 'Kadınlar Basketbol Süper Ligi'),
    ('TBL', 'Türkiye Basketbol Ligi'),
    ('TKBL', 'Türkiye Kadınlar Basketbol Ligi'),
    ('TB2L', 'Türkiye Basketbol 2. Ligi'),
    ('BGL', 'Basketbol Gençler Ligi Erkekler'),
    ('BGLK', 'Basketbol Gençler Ligi Kızlar'),
    ('EBBL', 'Erkekler Bölgesel Basketbol Ligi'),
    ('KBBL', 'Kadınlar Bölgesel Basketbol Ligi'),
]


class Match(models.Model):
    league = models.CharField(max_length=10, choices=LEAGUE_CHOICES)
    season = models.CharField(max_length=20, blank=True)
    week = models.CharField(max_length=50, blank=True)
    match_date = models.DateTimeField(null=True, blank=True)
    home_team = models.CharField(max_length=100)
    away_team = models.CharField(max_length=100)
    venue = models.CharField(max_length=200, blank=True)
    score = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=50, blank=True)
    tbf_match_id = models.CharField(max_length=50, blank=True, unique=True)
    referees = models.ManyToManyField('Referee', through='MatchReferee', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['match_date']

    def __str__(self):
        return f"{self.league} | {self.home_team} vs {self.away_team}"


class Referee(models.Model):
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class MatchReferee(models.Model):
    ROLE_CHOICES = [
        ('1', '1. Hakem'),
        ('2', '2. Hakem'),
        ('3', '3. Hakem'),
        ('commissioner', 'Komiser'),
        ('other', 'Diğer'),
    ]
    match = models.ForeignKey(Match, on_delete=models.CASCADE)
    referee = models.ForeignKey(Referee, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='1')

    class Meta:
        unique_together = ('match', 'referee')

    def __str__(self):
        return f"{self.referee.name} - {self.match}"


class ScrapeLog(models.Model):
    league = models.CharField(max_length=10, choices=LEAGUE_CHOICES)
    scraped_at = models.DateTimeField(auto_now_add=True)
    success = models.BooleanField(default=False)
    matches_found = models.IntegerField(default=0)
    message = models.TextField(blank=True)

    class Meta:
        ordering = ['-scraped_at']

    def __str__(self):
        return f"{self.league} - {self.scraped_at:%Y-%m-%d %H:%M} - {'OK' if self.success else 'HATA'}"
