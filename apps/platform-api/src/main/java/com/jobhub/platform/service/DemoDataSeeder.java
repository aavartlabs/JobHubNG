package com.jobhub.platform.service;

import com.jobhub.platform.domain.*;
import com.jobhub.platform.repository.*;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
@RequiredArgsConstructor
@Slf4j
public class DemoDataSeeder {

    private final UserRepository userRepository;
    private final TenantRepository tenantRepository;
    private final RoleRepository roleRepository;
    private final PermissionRepository permissionRepository;
    private final UserRoleRepository userRoleRepository;
    private final RolePermissionRepository rolePermissionRepository;
    private final PasswordEncoder passwordEncoder;

    @EventListener(ApplicationReadyEvent.class)
    @Transactional
    public void seed() {
        if (tenantRepository.count() > 0) {
            log.info("Demo data already seeded, skipping.");
            return;
        }

        Tenant platform = tenantRepository.save(Tenant.builder()
            .tenantKey("JOBHUB_PLATFORM")
            .name("JobHub Platform")
            .build());

        Role adminRole = roleRepository.save(Role.builder().roleKey("ADMIN").displayName("Admin / Platform Ops").build());
        Role seekerRole = roleRepository.save(Role.builder().roleKey("JOB_SEEKER").displayName("Job Seeker").build());
        Role studentRole = roleRepository.save(Role.builder().roleKey("STUDENT").displayName("Student / Fresher").build());
        Role professionalRole = roleRepository.save(Role.builder().roleKey("PROFESSIONAL").displayName("Working Professional").build());
        Role recruiterRole = roleRepository.save(Role.builder().roleKey("RECRUITER").displayName("Recruiter / Hiring Manager").build());
        Role employerRole = roleRepository.save(Role.builder().roleKey("EMPLOYER").displayName("Company / Employer").build());

        Permission platformRead = permissionRepository.save(Permission.builder().permissionKey("PLATFORM_READ").description("Read platform shell").build());
        Permission profileRead = permissionRepository.save(Permission.builder().permissionKey("PROFILE_READ").description("Read own profile").build());
        Permission profileWrite = permissionRepository.save(Permission.builder().permissionKey("PROFILE_WRITE").description("Update own profile").build());
        Permission adminDataflowRead = permissionRepository.save(Permission.builder().permissionKey("ADMIN_DATAFLOW_READ").description("Read platform data-flow diagnostics").build());
        Permission userRead = permissionRepository.save(Permission.builder().permissionKey("USER_READ").description("Read users").build());
        Permission auditRead = permissionRepository.save(Permission.builder().permissionKey("AUDIT_READ").description("Read audit records").build());

        createUser("admin@jobhub.local", "Admin", platform, adminRole, platformRead, profileRead, profileWrite, adminDataflowRead, userRead, auditRead);
        createUser("seeker@jobhub.local", "Job Seeker", platform, seekerRole, platformRead, profileRead, profileWrite);
        createUser("fresher@jobhub.local", "Fresher", platform, studentRole, platformRead, profileRead, profileWrite);
        createUser("professional@jobhub.local", "Professional", platform, professionalRole, platformRead, profileRead, profileWrite);
        createUser("recruiter@jobhub.local", "Recruiter", platform, recruiterRole, platformRead, profileRead, profileWrite);
        createUser("employer@jobhub.local", "Employer", platform, employerRole, platformRead, profileRead, profileWrite);

        log.info("Demo data seeded: 1 tenant, 6 users, 6 roles, 6 permissions");
    }

    @SafeVarargs
    private final void createUser(String email, String displayName, Tenant tenant, Role role, Permission... permissions) {
        User user = userRepository.save(User.builder()
            .tenant(tenant)
            .email(email)
            .displayName(displayName)
            .passwordHash(passwordEncoder.encode("parrot421$"))
            .build());

        UserRole ur = new UserRole();
        ur.setUser(user);
        ur.setRole(role);
        userRoleRepository.save(ur);

        for (Permission perm : permissions) {
            RolePermission rp = new RolePermission();
            rp.setRole(role);
            rp.setPermission(perm);
            rolePermissionRepository.save(rp);
        }
    }
}
