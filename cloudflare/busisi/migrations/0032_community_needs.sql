CREATE TABLE community_needs_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE community_need_places (
    psgc_code TEXT PRIMARY KEY CHECK (
        length(psgc_code) = 10 AND psgc_code NOT GLOB '*[^0-9]*'
    ),
    parent_psgc_code TEXT REFERENCES community_need_places(psgc_code),
    name TEXT NOT NULL,
    geographic_level TEXT NOT NULL CHECK (
        geographic_level IN (
            'region', 'province_or_huc', 'city_or_municipality',
            'submunicipality', 'barangay'
        )
    ),
    census_date TEXT NOT NULL CHECK (census_date = '2024-07-01'),
    total_population INTEGER NOT NULL CHECK (total_population >= 0),
    household_population INTEGER NOT NULL CHECK (
        household_population >= 0 AND household_population <= total_population
    ),
    households INTEGER NOT NULL CHECK (
        households >= 0 AND households <= household_population
    ),
    source_url TEXT NOT NULL,
    source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64)
);

CREATE INDEX community_need_level_population
ON community_need_places (geographic_level, total_population DESC, psgc_code);

CREATE INDEX community_need_parent
ON community_need_places (parent_psgc_code, total_population DESC, psgc_code);

CREATE INDEX community_need_name
ON community_need_places (name, geographic_level, psgc_code);

CREATE TABLE community_need_hierarchy_gaps (
    parent_psgc_code TEXT PRIMARY KEY REFERENCES community_need_places(psgc_code),
    unallocated_population INTEGER NOT NULL CHECK (unallocated_population >= 0),
    unallocated_household_population INTEGER NOT NULL CHECK (
        unallocated_household_population >= 0
    ),
    unallocated_households INTEGER NOT NULL CHECK (unallocated_households >= 0),
    CHECK (
        unallocated_population > 0
        OR unallocated_household_population > 0
        OR unallocated_households > 0
    )
);
