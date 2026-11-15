// GZ 安环监测系统 - 移动端入口
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'pages/login_page.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setPreferredOrientations([
    DeviceOrientation.portraitUp,
    DeviceOrientation.portraitDown,
  ]);
  runApp(const GzApp());
}

class GzApp extends StatelessWidget {
  const GzApp({super.key});
  @override
  Widget build(BuildContext context) {
    const bgDark = Color(0xFF0D1117);
    final scheme = ColorScheme.dark(
      primary: const Color(0xFF2D9E60),
      onPrimary: Colors.white,
      secondary: const Color(0xFF58A6FF),
      surface: const Color(0xFF161B22),
    );
    return MaterialApp(
      title: 'GZ安环监测',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: scheme,
        scaffoldBackgroundColor: bgDark,
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFF161B22),
          foregroundColor: Color(0xFFE6EDF3),
          elevation: 0.5,
          centerTitle: false,
        ),
        cardTheme: CardThemeData(
          color: const Color(0xFF161B22),
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
            side: const BorderSide(color: Color(0xFF30363D)),
          ),
        ),
        dividerTheme: const DividerThemeData(color: Color(0xFF30363D), thickness: 0.6),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: const Color(0xFF21262D),
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(10),
            borderSide: const BorderSide(color: Color(0xFF30363D)),
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(10),
            borderSide: const BorderSide(color: Color(0xFF30363D)),
          ),
        ),
        navigationBarTheme: NavigationBarThemeData(
          backgroundColor: const Color(0xFF161B22),
          indicatorColor: const Color(0xFF1A6B3C).withOpacity(0.45),
          labelTextStyle: WidgetStatePropertyAll(
            const TextStyle(fontSize: 12, color: Color(0xFFE6EDF3)),
          ),
        ),
        datePickerTheme: DatePickerThemeData(
          backgroundColor: const Color(0xFF161B22),
          headerForegroundColor: const Color(0xFFE6EDF3),
        ),
      ),
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: const [Locale('zh'), Locale('en')],
      locale: const Locale('zh'),
      home: const LoginPage(),
    );
  }
}
