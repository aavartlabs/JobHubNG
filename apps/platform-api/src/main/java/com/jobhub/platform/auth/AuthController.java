package com.jobhub.platform.auth;

import jakarta.validation.Valid;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/v1/auth")
public class AuthController {
    private final AuthService service;
    public AuthController(AuthService service) { this.service=service; }

    @PostMapping("/demo-login")
    public AuthDtos.LoginResponse login(@Valid @RequestBody AuthDtos.LoginRequest request) { return service.login(request); }

    @GetMapping("/me")
    public AuthDtos.UserView me(@AuthenticationPrincipal Jwt jwt) {
        List<String> roles = jwt.getClaimAsStringList("roles");
        List<String> perms = jwt.getClaimAsStringList("permissions");
        return new AuthDtos.UserView(Long.parseLong(jwt.getSubject()),jwt.getClaimAsString("email"),jwt.getClaimAsString("name"),jwt.getClaimAsString("tenant"),roles,perms);
    }
}
