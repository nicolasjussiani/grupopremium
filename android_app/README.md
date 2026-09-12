# PremiumBR Android

Aplicativo Android leve para a Central Mobile do ERP.

## Desenvolvimento

1. Instale Android Studio com Android SDK 35 e JDK 17 ou superior.
2. Abra a pasta `android_app` no Android Studio.
3. Execute a configuração `app` ou rode `gradlew.bat assembleDebug`.

O APK de testes é gerado em `app/build/outputs/apk/debug/app-debug.apk`.

## Segurança

- O WebView aceita navegação interna somente pelo HTTPS do ERP.
- Links externos são encaminhados ao navegador do aparelho.
- A sessão é mantida pelos cookies seguros do Django.
- Acesso local a arquivos e conteúdo pelo WebView permanece desativado.
