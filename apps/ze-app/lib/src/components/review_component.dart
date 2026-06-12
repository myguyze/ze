import 'package:ze_app/src/components/review.dart';

class ReviewComponent {
  const ReviewComponent({
    required this.id,
    required this.title,
    required this.items,
    this.approveLabel = 'Save',
    this.rejectLabel = 'Edit',
  });

  final String id;
  final String title;
  final List<ReviewItem> items;
  final String approveLabel;
  final String rejectLabel;

  factory ReviewComponent.fromJson(Map<String, dynamic> json) => ReviewComponent(
        id: json['id'] as String,
        title: json['title'] as String,
        items: (json['items'] as List<dynamic>? ?? [])
            .map((item) => ReviewItem.fromJson(item as Map<String, dynamic>))
            .toList(),
        approveLabel: json['approve_label'] as String? ?? 'Save',
        rejectLabel: json['reject_label'] as String? ?? 'Edit',
      );
}