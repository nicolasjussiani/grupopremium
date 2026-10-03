# PremiumBR Android

Aplicativo Android leve para a Central Mobile do ERP.

## Desenvolvimento

1. Instale Android Studio com Android SDK 35 e JDK 17 ou superior.
2. Abra a pasta `android_app` no Android Studio.
3. Execute a configuração `app` ou rode `gradlew.bat assembleDebug`.

O APK de testes é gerado em `app/build/outputs/apk/debug/app-debug.apk`.

## APK para instalação

O APK de distribuição assinado está em `../output/android/PremiumBR-Android-v1.0.0.apk`.
Ele usa o sistema publicado em `https://teste-eight-tau-53.vercel.app/mobile/`,
exige internet e aceita os mesmos usuários e permissões do sistema web.
Compatível com Android 7.0 ou superior. As instruções de instalação estão em
`../output/android/LEIA-ME.txt`.

Para compilar a versão de distribuição, use `gradlew.bat assembleRelease`, com
o JDK do Android Studio e `ANDROID_HOME` apontando para o SDK instalado. O APK
sem assinatura fica em `app/build/outputs/apk/release/app-release-unsigned.apk`
e deve ser assinado com `apksigner` antes da distribuição.

A chave desta distribuição e sua senha protegida estão fora do repositório,
em `%USERPROFILE%/.codex/android-signing/premiumbr/`. Preserve a chave para
assinar futuras atualizações. A senha no arquivo `password.xml` usa a proteção
da conta Windows que criou o arquivo; não envie esses arquivos junto com o APK.

Neste computador, a compilação precisa destas opções do Java para evitar uma
falha de conexão local do Gradle: `-Djava.net.preferIPv4Stack=true` e
`-Djdk.net.unixdomain.tmpdir=<pasta inexistente dentro do projeto>`.

## Segurança

- O WebView aceita navegação interna somente pelo HTTPS do ERP.
- Links externos são encaminhados ao navegador do aparelho.
- A sessão é mantida pelos cookies seguros do Django.
- Acesso local a arquivos e conteúdo pelo WebView permanece desativado.
