import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uni_links/uni_links.dart';
import 'package:ze_app/app.dart';
import 'package:ze_app/src/navigation/deep_link_handler.dart';

void main() {
  runApp(const ProviderScope(child: ZeApp()));
}
