package com.jobhub.platform.auth;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import java.util.List;

public final class AuthDtos {
  private AuthDtos() {}
  public record LoginRequest(@Email @NotBlank String email, @NotBlank String password) {}
  public record LoginResponse(String accessToken, long expiresInSeconds, UserView user) {}
  public record UserView(long id, String email, String displayName, String tenantKey, List<String> roles, List<String> permissions) {}
}
