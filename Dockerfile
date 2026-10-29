FROM mirror.gcr.io/library/debian:bookworm-slim@sha256:99c0b25c46d0214d5a2091092e7908907dcaecd6a962cde0ac700acee222b6f3 AS asar

ARG ASAR_REF=v1.81

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth=1 --branch "${ASAR_REF}" https://github.com/RPGHacker/asar.git /src/asar \
    && cmake -S /src/asar/src -B /build -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /build --parallel

RUN cp /build/asar/asar-standalone /usr/local/bin/asar \
    && /usr/local/bin/asar --version | grep -q "^Asar 1.81,"

FROM mirror.gcr.io/library/debian:bookworm-slim@sha256:99c0b25c46d0214d5a2091092e7908907dcaecd6a962cde0ac700acee222b6f3 AS emulator

ARG SNES9X_REF=1.63
ARG SDD1EMU_SHA256=a5f9733418ae913e8ebb358b7dde55504a88b2b035aadaf5496e229071b30770

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git ca-certificates make \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth=1 --branch "${SNES9X_REF}" \
        https://github.com/snes9xgit/snes9x.git /src/snes9x

RUN echo "${SDD1EMU_SHA256}  /src/snes9x/sdd1emu.cpp" | sha256sum --check --strict

RUN sed -i 's|^inline uint8 S9xGetByte (uint32 Address)\n{|&|' /src/snes9x/getset.h \
    && sed -i 's|^inline uint8 S9xGetByte (uint32 Address)$|extern unsigned long sf_bank_reads[256];\ninline uint8 S9xGetByte (uint32 Address)|' /src/snes9x/getset.h \
    && sed -i '0,/^{$/{}' /src/snes9x/getset.h \
    && perl -0pi -e 's/(inline uint8 S9xGetByte \(uint32 Address\)\n\{)/$1\n\tsf_bank_reads[(Address >> 16) & 0xFF]++;/' /src/snes9x/getset.h \
    && grep -c "sf_bank_reads" /src/snes9x/getset.h

RUN perl -0pi -e 's/(inline void S9xSetByte \(uint8 Byte, uint32 Address\)\n\{)/extern "C" void sf_note_write(uint32);\n$1\n\tsf_note_write(Address);/' /src/snes9x/getset.h \
    && grep -c "sf_note_write" /src/snes9x/getset.h

RUN perl -0pi -e 's/(inline void S9xSetWord \(uint16 Word, uint32 Address, enum s9xwrap_t w = WRAP_NONE, enum s9xwriteorder_t o = WRITE_01\)\n\{)/extern "C" void sf_note_write_word(uint32);\n$1\n\tsf_note_write_word(Address);/' /src/snes9x/getset.h \
    && grep -c "sf_note_write_word" /src/snes9x/getset.h

RUN perl -0pi -e 's/(\tsf_bank_reads\[\(Address >> 16\) & 0xFF\]\+\+;)/$1\n\tsf_note_read(Address);/' /src/snes9x/getset.h \
    && perl -0pi -e 's/(extern unsigned long sf_bank_reads\[256\];)/$1\nextern "C" void sf_note_read(uint32);/' /src/snes9x/getset.h \
    && grep -c "sf_note_read" /src/snes9x/getset.h

RUN sed -i 's|\tint32\tcount = d->TransferBytes;|\tint32\tcount = d->TransferBytes;\n\tif (getenv("SFDMA")) fprintf(stderr, "DMA ch=%d src=%02X:%04X n=%d b=%02X fixed=%d pc=%06X\\n", (int)(d - DMA), d->ABank, d->AAddress, (int)d->TransferBytes, d->BAddress, (int)d->AAddressFixed, (unsigned)Registers.PBPC);|' /src/snes9x/dma.cpp \
    && grep -c "SFDMA" /src/snes9x/dma.cpp

WORKDIR /src/snes9x/libretro
RUN make STATIC_LINKING=1 -j"$(nproc)" \
    && cp snes9x_libretro.so /src/snes9x/libretro/snes9x_libretro.a

COPY emu/main.cpp /src/frontend/main.cpp
COPY emu/windowed_lorom.cpp /src/frontend/windowed_lorom.cpp
COPY emu/windowed_lorom.h /src/frontend/windowed_lorom.h

RUN g++ -O2 -std=c++11 -o /src/sfemu /src/frontend/main.cpp /src/frontend/windowed_lorom.cpp \
        -I/src/frontend -I/src/snes9x -I/src/snes9x/libretro -I/src/snes9x/libretro/libretro-common/include \
        -I/src/snes9x/apu -I/src/snes9x/apu/bapu \
        /src/snes9x/libretro/snes9x_libretro.a

FROM mirror.gcr.io/library/debian:bookworm-slim@sha256:99c0b25c46d0214d5a2091092e7908907dcaecd6a962cde0ac700acee222b6f3 AS reference

ARG SNES9X_REF=1.63
ARG SDD1EMU_SHA256=a5f9733418ae913e8ebb358b7dde55504a88b2b035aadaf5496e229071b30770

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth=1 --branch "${SNES9X_REF}" \
        https://github.com/snes9xgit/snes9x.git /src/snes9x

WORKDIR /ref

RUN cp /src/snes9x/sdd1emu.cpp /src/snes9x/sdd1emu.h /ref/ \
    && echo "${SDD1EMU_SHA256}  /ref/sdd1emu.cpp" | sha256sum --check --strict

COPY ref/port.h ref/driver.cpp /ref/

RUN g++ -O2 -Wall -Wextra -I/ref -o /ref/sdd1ref /ref/driver.cpp /ref/sdd1emu.cpp

FROM mirror.gcr.io/library/python:3.15.2-slim-bookworm@sha256:4e03260adeeebafccd084f3584e6b84823aba5651cfb53ef8a078ed441ddf9cd AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && git config --system --add safe.directory '*'

COPY --from=asar /usr/local/bin/asar /usr/local/bin/asar
COPY --from=emulator /src/sfemu /usr/local/bin/sfemu
COPY --from=reference /ref/sdd1ref /usr/local/bin/sdd1ref

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp

WORKDIR /work

FROM runtime AS gates

COPY --from=mirror.gcr.io/library/node:24.16.0-bookworm-slim@sha256:2c87ef9bd3c6a3bd4b472b4bec2ce9d16354b0c574f736c476489d09f560a203 /usr/local /usr/local

RUN apt-get update && apt-get install -y --no-install-recommends shellcheck curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ARG ACTIONLINT=1.7.12

RUN arch="$(dpkg --print-architecture)" \
    && case "${arch}" in \
        amd64) sum=8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8 ;; \
        arm64) sum=325e971b6ba9bfa504672e29be93c24981eeb1c07576d730e9f7c8805afff0c6 ;; \
        *) echo "no actionlint digest for ${arch}" >&2 && exit 1 ;; \
    esac \
    && curl -fsSL -o /tmp/actionlint.tar.gz \
        "https://github.com/rhysd/actionlint/releases/download/v${ACTIONLINT}/actionlint_${ACTIONLINT}_linux_${arch}.tar.gz" \
    && echo "${sum}  /tmp/actionlint.tar.gz" | sha256sum --check --strict \
    && tar -xzf /tmp/actionlint.tar.gz -C /usr/local/bin actionlint \
    && rm /tmp/actionlint.tar.gz

COPY --from=ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 /uv /usr/local/bin/uv

RUN uv pip install --system --no-cache \
        ruff==0.16.3 mypy==1.14.1 coverage==7.6.10 yamllint==1.38.0

ENV COREPACK_HOME=/opt/corepack \
    PATH=/opt/tooling/node_modules/.bin:$PATH

COPY package.json pnpm-lock.yaml /opt/tooling/

RUN cd /opt/tooling \
    && corepack pnpm install --frozen-lockfile --ignore-scripts \
    && chmod -R a+rX /opt/corepack /opt/tooling
