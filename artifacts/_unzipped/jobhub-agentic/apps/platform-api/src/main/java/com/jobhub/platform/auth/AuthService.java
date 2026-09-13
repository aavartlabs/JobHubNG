package com.jobhub.platform.auth;

import com.jobhub.platform.common.AuditOutboxService;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@Service
public class AuthService {
    private final AuthRepository repo;
    private final JdbcTemplate jdbc;
    private final PasswordEncoder encoder;
    private final JwtEncoder jwtEncoder;
    private final AuditOutboxService audit;

    public AuthService(AuthRepository repo, JdbcTemplate jdbc, PasswordEncoder encoder, JwtEncoder jwtEncoder, AuditOutboxService audit) {
        this.repo=repo; this.jdbc=jdbc; this.encoder=encoder; this.jwtEncoder=jwtEncoder; this.audit=audit;
    }

    public AuthDtos.LoginResponse login(AuthDtos.LoginRequest req) {
        Map<String,Object> u;
        try { u = repo.findUserByEmail(req.email()); }
        catch (Exception e) { throw new IllegalArgumentException("Invalid email or password"); }
        if (!encoder.matches(req.password(), String.valueOf(u.get("password_hash")))) throw new IllegalArgumentException("Invalid email or password");
        if (!"ACTIVE".equals(u.get("status"))) throw new IllegalStateException("User is inactive");
        long id = ((Number)u.get("id")).longValue();
        String tenant = String.valueOf(u.get("tenant_key"));
        long tenantId = jdbc.queryForObject("SELECT id FROM tenants WHERE tenant_key=?", Long.class, tenant);
        List<String> roles = repo.findRoles(id);
        List<String> perms = repo.findPermissions(id);
        Instant now = Instant.now(); Instant exp = now.plusSeconds(3600);
        JwtClaimsSet claims = JwtClaimsSet.builder().issuer("jobhub").subject(String.valueOf(id)).issuedAt(now).expiresAt(exp)
          .id(UUID.randomUUID().toString()).claim("email",u.get("email")).claim("name",u.get("display_name"))
          .claim("tenant",tenant).claim("roles",roles).claim("permissions",perms).build();
        String token = jwtEncoder.encode(JwtEncoderParameters.from(JwsHeader.with(MacAlgorithm.HS256).build(),claims)).getTokenValue();
        String correlationId = UUID.randomUUID().toString();
        audit.recordLogin(id, tenantId, String.valueOf(u.get("email")), correlationId);
        return new AuthDtos.LoginResponse(token,3600,new AuthDtos.UserView(id,String.valueOf(u.get("email")),String.valueOf(u.get("display_name")),tenant,roles,perms));
    }
}
