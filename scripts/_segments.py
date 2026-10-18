"""Property segments shared by the sale and rent aggregates.

One `rooms` vocabulary for both: home buckets (studio … 4br+, villa) plus non-home
segments. Headline numbers (pages, FAQ, masks, app) use homes; the panel charts
every bucket, so offices, labor camps or land plots stay visible but never
leak into a district's "median rent".
"""

HOME_ROOMS = ('studio', '1br', '2br', '3br', '4br+', 'villa')
RENT_SEGMENTS = ('office', 'shop', 'warehouse', 'labor', 'other')

HOME_SQL = "rooms IN ('studio','1br','2br','3br','4br+','villa')"

# Ejari: one row per line item; bedroom buckets only for apartment types
RENT_ROOMS_SQL = """CASE
  WHEN ejari_property_type_en IN ('Villa', 'Complex Villas') THEN 'villa'
  WHEN ejari_property_type_en IN ('Flat', 'Studio', 'Penthouse', 'Hotel apartments') THEN
    CASE
      WHEN ejari_property_type_en = 'Penthouse'          THEN '4br+'
      WHEN ejari_property_sub_type_en ILIKE '%studio%'   THEN 'studio'
      WHEN ejari_property_sub_type_en ILIKE 'penthouse%' THEN '4br+'
      WHEN ejari_property_sub_type_en ILIKE '1%bed%'     THEN '1br'
      WHEN ejari_property_sub_type_en ILIKE '2%bed%'     THEN '2br'
      WHEN ejari_property_sub_type_en ILIKE '3%bed%'     THEN '3br'
      WHEN ejari_property_sub_type_en ILIKE '4%bed%'
        OR ejari_property_sub_type_en ILIKE '5%bed%'
        OR ejari_property_sub_type_en ILIKE '6%bed%'     THEN '4br+'
      ELSE 'other'
    END
  WHEN ejari_property_type_en = 'Office' THEN 'office'
  WHEN ejari_property_type_en IN ('Shop', 'Showroom', 'Restaurant', 'Clinic', 'Kiosk', 'Shopping Center') THEN 'shop'
  WHEN ejari_property_type_en IN ('Warehouse', 'Warehouse complex', 'Workshop', 'Store', 'OPEN STORAGE SHED') THEN 'warehouse'
  WHEN ejari_property_type_en IN ('Labor Camps', 'Staff Accommodation', 'Portacabin') THEN 'labor'
  ELSE 'other'
END"""

SALE_SEGMENTS = ('land', 'commercial', 'other')

# DLD registers many villa/townhouse sales as Land (DAMAC Hills 2/Lagoons, Mudon, The Oasis…):
# a named project on a plot under 1,500 m² is a villa, not a land deal
SALE_VILLA_PLOT_SQL = ("(property_type_en = 'Land' AND project_name_en IS NOT NULL "
                       "AND TRY_CAST(procedure_area AS DOUBLE) < 1500)")

# Over the fixed pt / sbt / rooms columns of the sale base table
SALE_ROOMS_SQL = """CASE
  WHEN sbt = 'Villa' THEN 'villa'
  WHEN sbt IN ('Flat', 'Hotel Apartment') THEN
    CASE
      WHEN TRIM(rooms) IN ('Studio', 'Single Room') THEN 'studio'
      WHEN TRIM(rooms) = '1 B/R' THEN '1br'
      WHEN TRIM(rooms) = '2 B/R' THEN '2br'
      WHEN TRIM(rooms) = '3 B/R' THEN '3br'
      WHEN TRIM(rooms) IN ('4 B/R', '5 B/R', '6 B/R', '7 B/R', 'PENTHOUSE') THEN '4br+'
      ELSE 'other'
    END
  WHEN pt = 'Land' THEN 'land'
  WHEN pt = 'Unit' THEN 'commercial'
  ELSE 'other'
END"""

# Legacy flat / villa / commercial / land split (sale record fields, app by_type)
SALE_BUCKET_SQL = """CASE WHEN sbt = 'Villa' THEN 'villa' WHEN sbt IN ('Flat', 'Hotel Apartment') THEN 'flat'
  WHEN pt = 'Land' THEN 'land' ELSE 'commercial' END"""
