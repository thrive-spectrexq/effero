# Stage 1: Build Rust safety kernel
FROM rust:1.85-slim AS rust-builder
WORKDIR /build
COPY Cargo.toml rust-toolchain.toml ./
COPY crates/ crates/
RUN cargo build --release -p effero-safety-kernel

# Stage 2: Python runtime
FROM python:3.12-slim
WORKDIR /app

# Copy safety kernel binary
COPY --from=rust-builder /build/target/release/effero-safety-kerneld /usr/local/bin/

# Install Python package
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir ".[all]"

# Default ports
EXPOSE 9400 8080

CMD ["effero", "run"]
