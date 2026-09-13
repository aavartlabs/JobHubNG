package com.jobhub.platform.common;

import com.jobhub.platform.auth.AuthRepository;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

@Component
public class DemoDataSeeder implements ApplicationRunner {
    private final JdbcTemplate jdbc;
    private final PasswordEncoder encoder;
    private final AuthRepository repo;
    public DemoDataSeeder(JdbcTemplate jdbc, PasswordEncoder encoder, AuthRepository repo) { this.jdbc=jdbc; this.encoder=encoder; this.repo=repo; }

    @Override public void run(ApplicationArguments args) {
        Long tenantId = jdbc.queryForObject("SELECT id FROM tenants WHERE tenant_key='JOBHUB_PLATFORM'", Long.class);
        String hash = encoder.encode("password");
        repo.ensureDemoUser("seeker@jobhub.local","Sarah Ahmed",hash,"JOB_SEEKER",tenantId);
        repo.ensureDemoUser("fresher@jobhub.local","Rahul Sharma",hash,"STUDENT",tenantId);
        repo.ensureDemoUser("professional@jobhub.local","Kiran Patel",hash,"PROFESSIONAL",tenantId);
        repo.ensureDemoUser("recruiter@jobhub.local","Riya Mehta",hash,"RECRUITER",tenantId);
        repo.ensureDemoUser("employer@jobhub.local","Neha Thomas",hash,"EMPLOYER",tenantId);
        repo.ensureDemoUser("admin@jobhub.local","Aman Oberoi",hash,"ADMIN",tenantId);
    }
}
