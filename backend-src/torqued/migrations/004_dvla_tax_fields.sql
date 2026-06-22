-- Promote the rest of the DVLA VES response to queryable columns. The verbatim
-- payload already lives in dvla_vehicles.raw_json (nothing was lost); these make
-- every remaining scalar field explicit, mirroring how dvsa_vehicles stores MOT.
ALTER TABLE dvla_vehicles ADD COLUMN make                            TEXT;
ALTER TABLE dvla_vehicles ADD COLUMN colour                          TEXT;
ALTER TABLE dvla_vehicles ADD COLUMN fuel_type                       TEXT;
ALTER TABLE dvla_vehicles ADD COLUMN year_of_manufacture             INTEGER;
ALTER TABLE dvla_vehicles ADD COLUMN engine_capacity                 INTEGER;
ALTER TABLE dvla_vehicles ADD COLUMN co2_emissions                   INTEGER;
ALTER TABLE dvla_vehicles ADD COLUMN marked_for_export               INTEGER;
ALTER TABLE dvla_vehicles ADD COLUMN type_approval                   TEXT;
ALTER TABLE dvla_vehicles ADD COLUMN wheelplan                       TEXT;
ALTER TABLE dvla_vehicles ADD COLUMN revenue_weight                  INTEGER;
ALTER TABLE dvla_vehicles ADD COLUMN real_driving_emissions          TEXT;
ALTER TABLE dvla_vehicles ADD COLUMN euro_status                     TEXT;
ALTER TABLE dvla_vehicles ADD COLUMN date_of_last_v5c_issued         TEXT;
ALTER TABLE dvla_vehicles ADD COLUMN month_of_first_registration     TEXT;
ALTER TABLE dvla_vehicles ADD COLUMN month_of_first_dvla_registration TEXT;
ALTER TABLE dvla_vehicles ADD COLUMN art_end_date                    TEXT;
ALTER TABLE dvla_vehicles ADD COLUMN automated_vehicle               INTEGER;
