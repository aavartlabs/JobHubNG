package com.jobhub.platform.service;

import com.jobhub.platform.domain.*;
import com.jobhub.platform.repository.*;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class AuthService {
    private final UserRepository userRepository;
    private final RoleRepository roleRepository;
    private final UserRoleRepository userRoleRepository;
    private final RolePermissionRepository rolePermissionRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtEncoder jwtEncoder;
    private final AuditService auditService;

    @Transactional
    public LoginResponse login(LoginRequest req) {
        User user = userRepository.findByEmail(req.email())
            .orElseThrow(() -> new IllegalArgumentException("Invalid email or password"));

        if (!passwordEncoder.matches(req.password(), user.getPasswordHash())) {
            throw new IllegalArgumentException("Invalid email or password");
        }
        if (!"ACTIVE".equals(user.getStatus())) {
            throw new IllegalStateException("User is inactive");
        }

        Tenant tenant = user.getTenant();
        List<String> roles = userRoleRepository.findRoleKeysByUserId(user.getId());

        List<String> permissions = new ArrayList<>();
        for (String roleKey : roles) {
            Role role = roleRepository.findByRoleKey(roleKey).orElse(null);
            if (role != null) {
                permissions.addAll(rolePermissionRepository.findPermissionKeysByRoleId(role.getId()));
            }
        }

        Instant now = Instant.now();
        Instant exp = now.plusSeconds(3600);
        JwtClaimsSet claims = JwtClaimsSet.builder()
            .issuer("jobhub")
            .subject(String.valueOf(user.getId()))
            .issuedAt(now)
            .expiresAt(exp)
            .id(UUID.randomUUID().toString())
            .claim("email", user.getEmail())
            .claim("name", user.getDisplayName())
            .claim("tenant", tenant != null ? tenant.getTenantKey() : "NONE")
            .claim("roles", roles)
            .claim("permissions", permissions)
            .build();
        String token = jwtEncoder.encode(JwtEncoderParameters.from(
            JwsHeader.with(MacAlgorithm.HS256).build(), claims)).getTokenValue();

        String correlationId = UUID.randomUUID().toString();
        auditService.recordLogin(user.getId(), tenant != null ? tenant.getId() : null,
            user.getEmail(), correlationId);

        return new LoginResponse(token, 3600,
            new UserProfile(user.getId(), user.getEmail(), user.getDisplayName(),
                tenant != null ? tenant.getTenantKey() : "NONE", roles, permissions));
    }

    public record LoginRequest(String email, String password) {}
    public record LoginResponse(String token, int expiresIn, UserProfile user) {}
    public record UserView(Long id, String email, String name, String tenant, List<String> roles, List<String> permissions) {}
    public record UserProfile(Long id, String email, String displayName, String tenantKey, List<String> roles, List<String> permissions) {}
}
