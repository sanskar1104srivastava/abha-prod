from __future__ import annotations

import base64
import hashlib
import secrets
import uuid

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat, load_der_public_key


_C25519_P = (1 << 255) - 19
_C25519_W_A = 0x2AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA984914A144
_C25519_W_GX = 0x2AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD245A
_C25519_W_GY = 0x20AE19A1B8A086B4E01EDD2C7748D14C923D4D7E6D7C61B229E9C5A27ECED3D9
_C25519_W_N = 0x1000000000000000000000000000000014DEF9DEA2F79CD65812631A5CF5D3ED


def _wc25519_add(left: tuple[int, int] | None, right: tuple[int, int] | None) -> tuple[int, int] | None:
    if left is None:
        return right
    if right is None:
        return left
    x1, y1 = left
    x2, y2 = right
    if x1 == x2:
        if (y1 + y2) % _C25519_P == 0:
            return None
        slope = (3 * x1 * x1 + _C25519_W_A) * pow(2 * y1, _C25519_P - 2, _C25519_P) % _C25519_P
    else:
        slope = (y2 - y1) * pow(x2 - x1, _C25519_P - 2, _C25519_P) % _C25519_P
    x3 = (slope * slope - x1 - x2) % _C25519_P
    y3 = (slope * (x1 - x3) - y1) % _C25519_P
    return x3, y3


def _wc25519_mul(scalar: int, point: tuple[int, int]) -> tuple[int, int] | None:
    result: tuple[int, int] | None = None
    addend: tuple[int, int] | None = point
    while scalar:
        if scalar & 1:
            result = _wc25519_add(result, addend)
        addend = _wc25519_add(addend, addend)
        scalar >>= 1
    return result


def _wc25519_spki(rawPoint: bytes) -> bytes:
    oidEcPublicKey = bytes.fromhex("06072a8648ce3d0201")
    oidCurve25519 = bytes.fromhex("060a2b060104019755010501")
    algSeq = bytes([0x30, 21]) + oidEcPublicKey + oidCurve25519
    bitString = bytes([0x03, len(rawPoint) + 1, 0x00]) + rawPoint
    spkiBody = algSeq + bitString
    return bytes([0x30, len(spkiBody)]) + spkiBody


def _wc25519_public_point(publicBytes: bytes) -> bytes:
    if len(publicBytes) == 65 and publicBytes[0] == 0x04:
        return publicBytes
    if len(publicBytes) >= 65 and publicBytes[-65] == 0x04:
        return publicBytes[-65:]
    marker = b"\x03\x42\x00\x04"
    markerIndex = publicBytes.find(marker)
    if markerIndex >= 0 and len(publicBytes) >= markerIndex + len(marker) + 64:
        return b"\x04" + publicBytes[markerIndex + len(marker):markerIndex + len(marker) + 64]
    raise ValueError("Unsupported Curve25519 public key format")


def _wc25519_generate_keypair(publicKeyFormat: str = "publicKey") -> tuple[str, str, str]:
    scalar = int.from_bytes(secrets.token_bytes(32), "big") % (_C25519_W_N - 1) + 1
    publicPoint = _wc25519_mul(scalar, (_C25519_W_GX, _C25519_W_GY))
    if publicPoint is None:
        return _wc25519_generate_keypair(publicKeyFormat)
    rawPoint = bytes([0x04]) + publicPoint[0].to_bytes(32, "big") + publicPoint[1].to_bytes(32, "big")
    publicBytes = _wc25519_spki(rawPoint) if publicKeyFormat == "x509PublicKey" else rawPoint
    return (
        base64.b64encode(scalar.to_bytes(32, "big")).decode("utf-8"),
        base64.b64encode(publicBytes).decode("utf-8"),
        AbdmCryptoService.randomNonce(),
    )


def _wc25519_ecdh(ourPrivateKeyB64: str, theirPublicBytes: bytes) -> bytes:
    scalar = int.from_bytes(base64.b64decode(ourPrivateKeyB64), "big")
    rawPoint = _wc25519_public_point(theirPublicBytes)
    x = int.from_bytes(rawPoint[1:33], "big")
    y = int.from_bytes(rawPoint[33:65], "big")
    sharedPoint = _wc25519_mul(scalar, (x, y))
    if sharedPoint is None:
        raise ValueError("Weierstrass Curve25519 ECDH shared point is invalid")
    return sharedPoint[0].to_bytes(32, "big")


class AbdmCryptoService:
    @staticmethod
    def newRequestId() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def newTrackingId() -> str:
        return f"trk_{uuid.uuid4().hex}"

    @staticmethod
    def newEventId() -> str:
        return f"evt_{uuid.uuid4().hex}"

    @staticmethod
    def checksumBase64(content: str) -> str:
        digest = hashlib.sha256(content.encode("utf-8")).digest()
        return base64.b64encode(digest).decode("utf-8")

    @staticmethod
    def randomNonce() -> str:
        return base64.b64encode(secrets.token_bytes(32)).decode("utf-8")

    @staticmethod
    def rsaEncryptOaep(plainText: str, publicKeyB64: str) -> str:
        """RSA/ECB/OAEPWithSHA-1AndMGF1Padding — required by ABDM ABHA v3."""
        der = base64.b64decode(publicKeyB64)
        pubKey = load_der_public_key(der)
        cipher = pubKey.encrypt(
            plainText.encode("utf-8"),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA1()),  # noqa: S303
                algorithm=hashes.SHA1(),  # noqa: S303
                label=None,
            ),
        )
        return base64.b64encode(cipher).decode("utf-8")

    @staticmethod
    def generateRawEcdhKeypair() -> tuple[str, str, str]:
        privateKey = X25519PrivateKey.generate()
        privateKeyB64 = base64.b64encode(
            privateKey.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        ).decode("utf-8")
        publicKeyB64 = base64.b64encode(privateKey.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode("utf-8")
        return privateKeyB64, publicKeyB64, AbdmCryptoService.randomNonce()

    @staticmethod
    def generateFideliusEcdhKeypair(publicKeyFormat: str = "publicKey") -> tuple[str, str, str]:
        return _wc25519_generate_keypair(publicKeyFormat)

    @staticmethod
    def generateEcdhKeypairForPeer(theirPublicKeyB64: str) -> tuple[str, str, str]:
        theirPublicBytes = base64.b64decode(theirPublicKeyB64)
        if len(theirPublicBytes) == 32:
            return AbdmCryptoService.generateRawEcdhKeypair()
        return AbdmCryptoService.generateFideliusEcdhKeypair()

    @staticmethod
    def rawKeyMaterial(publicKeyB64: str, nonceB64: str, expiry: str) -> dict[str, object]:
        return AbdmCryptoService.keyMaterial(publicKeyB64, nonceB64, expiry)

    @staticmethod
    def keyMaterial(publicKeyB64: str, nonceB64: str, expiry: str, curve: str = "Curve25519") -> dict[str, object]:
        return {
            "cryptoAlg": "ECDH",
            "curve": curve,
            "dhPublicKey": {
                "expiry": expiry,
                "parameters": "Curve25519/32byte random key",
                "keyValue": publicKeyB64,
            },
            "nonce": nonceB64,
        }

    @staticmethod
    def ecdhEncrypt(
        plaintext: str,
        ourPrivateKeyB64: str,
        ourNonceB64: str,
        theirPublicKeyB64: str,
        theirNonceB64: str,
    ) -> str:
        aesKey, gcmIv = AbdmCryptoService.deriveAesGcmParams(
            ourPrivateKeyB64,
            ourNonceB64,
            theirPublicKeyB64,
            theirNonceB64,
        )
        ciphertext = AESGCM(aesKey).encrypt(gcmIv, plaintext.encode("utf-8"), None)
        return base64.b64encode(ciphertext).decode("utf-8")

    @staticmethod
    def ecdhDecrypt(
        ciphertextB64: str,
        ourPrivateKeyB64: str,
        ourNonceB64: str,
        theirPublicKeyB64: str,
        theirNonceB64: str,
    ) -> str:
        aesKey, gcmIv = AbdmCryptoService.deriveAesGcmParams(
            ourPrivateKeyB64,
            ourNonceB64,
            theirPublicKeyB64,
            theirNonceB64,
        )
        plaintext = AESGCM(aesKey).decrypt(gcmIv, base64.b64decode(ciphertextB64), None)
        return plaintext.decode("utf-8")

    @staticmethod
    def deriveAesGcmParams(
        ourPrivateKeyB64: str,
        ourNonceB64: str,
        theirPublicKeyB64: str,
        theirNonceB64: str,
    ) -> tuple[bytes, bytes]:
        theirPublicBytes = base64.b64decode(theirPublicKeyB64)
        if len(theirPublicBytes) == 32:
            sharedSecret = X25519PrivateKey.from_private_bytes(base64.b64decode(ourPrivateKeyB64)).exchange(
                X25519PublicKey.from_public_bytes(theirPublicBytes)
            )
            ourNonce = base64.b64decode(ourNonceB64)[:20]
            theirNonce = base64.b64decode(theirNonceB64)[:20]
            xorNonce = bytes(a ^ b for a, b in zip(ourNonce, theirNonce))
            aesKey = hashlib.sha256(sharedSecret + xorNonce).digest()[:32]
            return aesKey, xorNonce[:12]

        sharedSecret = _wc25519_ecdh(ourPrivateKeyB64, theirPublicBytes)
        ourNonce = base64.b64decode(ourNonceB64)
        theirNonce = base64.b64decode(theirNonceB64)
        xorNonce = bytes(a ^ b for a, b in zip(ourNonce, theirNonce))
        aesKey = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=xorNonce[:20],
            info=b"",
        ).derive(sharedSecret)
        return aesKey, xorNonce[-12:]

    @staticmethod
    def deriveRawAesGcmParams(
        ourPrivateKeyB64: str,
        ourNonceB64: str,
        theirPublicKeyB64: str,
        theirNonceB64: str,
    ) -> tuple[bytes, bytes]:
        return AbdmCryptoService.deriveAesGcmParams(
            ourPrivateKeyB64,
            ourNonceB64,
            theirPublicKeyB64,
            theirNonceB64,
        )
