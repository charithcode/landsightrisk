"""
MODULE M1 — Multi-Source Environmental Data Ingestion
======================================================
Fetches and merges all environmental data sources into a
unified feature matrix per grid cell / slope unit.

Inputs:
  - IMD / GPM IMERG rainfall grids
  - ISRO Bhuvan / NASA SMAP soil moisture
  - SRTM / ASTER Digital Elevation Model
  - Bhuvan / Sentinel-2 Land Cover (LULC)
  - Bhukosh / NGDR historical landslide inventory

Output:
  - data/processed/feature_matrix.csv
"""
