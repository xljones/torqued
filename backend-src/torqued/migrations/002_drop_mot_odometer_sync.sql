-- MOT odometer readings are now served directly from mot_tests; remove
-- the previously-synced copies from odometer_logs to eliminate duplication.
DELETE FROM odometer_logs WHERE source = 'mot';
