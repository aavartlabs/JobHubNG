INSERT INTO tenants(tenant_key,name) VALUES ('JOBHUB_PLATFORM','JobHub Platform') ON CONFLICT DO NOTHING;

INSERT INTO roles(role_key,display_name) VALUES
 ('JOB_SEEKER','Job Seeker'),
 ('STUDENT','Student / Fresher'),
 ('PROFESSIONAL','Working Professional'),
 ('RECRUITER','Recruiter / Hiring Manager'),
 ('EMPLOYER','Company / Employer'),
 ('ADMIN','Admin / Platform Ops')
ON CONFLICT DO NOTHING;

INSERT INTO permissions(permission_key,description) VALUES
 ('PLATFORM_READ','Read platform shell'),
 ('PROFILE_READ','Read own profile'),
 ('PROFILE_WRITE','Update own profile'),
 ('ADMIN_DATAFLOW_READ','Read platform data-flow diagnostics'),
 ('USER_READ','Read users'),
 ('AUDIT_READ','Read audit records')
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions(role_id,permission_id)
SELECT r.id,p.id FROM roles r CROSS JOIN permissions p
WHERE r.role_key IN ('JOB_SEEKER','STUDENT','PROFESSIONAL','RECRUITER','EMPLOYER')
  AND p.permission_key IN ('PLATFORM_READ','PROFILE_READ','PROFILE_WRITE')
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions(role_id,permission_id)
SELECT r.id,p.id FROM roles r CROSS JOIN permissions p
WHERE r.role_key='ADMIN'
ON CONFLICT DO NOTHING;
