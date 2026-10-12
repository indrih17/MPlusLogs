local _, MPL = ...
-- Transcribed from the user's supplied screenshot, not a live API result.
-- The screenshot shows All Specs, so it must not be represented as Guardian-only.
local profile = {
    name="Киндрих", realm="Гордунни", region="eu", realmSlug="gordunni", characterID=81818678,
    zone=55, season="Midnight M+ Season 2", spec="All specs", metric="dps",
    score=3774, best=37.4, median=22.4, runs=162,
    updated="Дата данных неизвестна", source="Снимок со скриншота пользователя", dungeons={
        {name="Altar of Fangs", level=19, time="29:26", runs=28, points=470, rank=1314, amount=194060, best=22, median=20},
        {name="Den of Nalorakk", level=19, time="29:51", runs=27, points=472, rank=1747, amount=168110, best=62, median=34},
        {name="Kings' Rest", level=19, time="31:45", runs=22, points=471, rank=1651, amount=128040, best=50, median=28},
        {name="Murder Row", level=19, time="29:10", runs=15, points=475, rank=790, amount=170790, best=49, median=15},
        {name="Ruby Life Pools", level=19, time="26:57", runs=16, points=471, rank=989, amount=199010, best=52, median=27},
        {name="Temple of Sethraliss", level=19, time="31:12", runs=20, points=470, rank=1762, amount=152210, best=11, median=11, flagged=true},
        {name="The Blinding Vale", level=19, time="28:49", runs=14, points=471, rank=1195, amount=185060, best=38, median=34},
        {name="Voidscar Arena", level=19, time="29:31", runs=21, points=470, rank=1509, amount=157950, best=15, median=10},
    }
}
MPL.snapshots = {[MPL.Key(profile.name, profile.realm, profile.region)] = profile}
