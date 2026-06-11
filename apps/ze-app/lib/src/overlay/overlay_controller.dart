import 'package:flutter/material.dart';

class OverlayController extends ChangeNotifier {
  bool _isOpen = false;
  String? _screenContext;
  String? _entityId;

  bool get isOpen => _isOpen;
  String? get screenContext => _screenContext;
  String? get entityId => _entityId;

  void open({String? screen, String? entityId}) {
    _isOpen = true;
    _screenContext = screen;
    _entityId = entityId;
    notifyListeners();
  }

  void close() {
    _isOpen = false;
    notifyListeners();
  }
}
