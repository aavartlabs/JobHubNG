package com.jobhub.platform.controller;

import com.jobhub.platform.service.AuthService;
import com.jobhub.platform.service.AuthService.LoginRequest;
import com.jobhub.platform.service.AuthService.LoginResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

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
    public Authentication me(Authentication auth) {
        return auth;
    }

    @GetMapping("/admin/ping")
    @PreAuthorize("hasRole('ADMIN')")
    public String adminPing() {
        return "pong from admin endpoint";
    }

    @GetMapping("/public/ping")
    public String publicPing() {
        return "pong from public endpoint";
    }
}
