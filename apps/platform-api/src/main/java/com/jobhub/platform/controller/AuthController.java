package com.jobhub.platform.controller;

import com.jobhub.platform.service.AuthService;
import com.jobhub.platform.service.AuthService.LoginRequest;
import com.jobhub.platform.service.AuthService.LoginResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import java.util.List;

@RestController
@RequestMapping("/api/v1")
@RequiredArgsConstructor
public class AuthController {

    private final AuthService authService;

    @PostMapping("/auth/demo-login")
    public LoginResponse login(@RequestBody LoginRequest request) {
        return authService.login(request);
    }

    @GetMapping("/auth/me")
    public AuthService.UserProfile me(Authentication auth) {
        var jwt = (org.springframework.security.oauth2.jwt.Jwt) auth.getPrincipal();
        var roles = jwt.getClaimAsStringList("roles");
        var perms = jwt.getClaimAsStringList("permissions");
        return new AuthService.UserProfile(
            Long.valueOf(jwt.getSubject()),
            jwt.getClaimAsString("email"),
            jwt.getClaimAsString("name"),
            jwt.getClaimAsString("tenant"),
            roles != null ? roles : List.of(),
            perms != null ? perms : List.of()
        );
    }

    @GetMapping("/admin/dataflow")
    @PreAuthorize("hasAuthority('ADMIN_DATAFLOW_READ')")
    public Map<String, Object> adminPing() {
        return Map.of(
            "service", "platform-api",
            "phase", "1.0",
            "status", "READY",
            "modules", List.of("auth", "audit", "outbox", "ai-runs")
        );
    }

    @GetMapping("/public/ping")
    public String publicPing() {
        return "pong from public endpoint";
    }
}
