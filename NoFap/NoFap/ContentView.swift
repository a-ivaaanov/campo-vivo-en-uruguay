import SwiftUI

// TODO: Убедитесь, что шрифты RF Dewi добавлены в проект и Info.plist

struct ContentView: View {
    // Сохраняем значения локально
    @AppStorage("streakCount") private var streakCount: Int = 0
    @AppStorage("lastCheckinTimestamp") private var lastCheckinTimestamp: Double = 0

    // Вычисляемое свойство для удобной работы с датой
    private var lastCheckinDate: Date? {
        guard lastCheckinTimestamp > 0 else { return nil }
        return Date(timeIntervalSince1970: lastCheckinTimestamp)
    }

    // Состояние для отображения сообщения (опционально)
    @State private var message: String = ""

    var body: some View {
        ZStack {
            // Черный фон
            Color.black.ignoresSafeArea()

            VStack(spacing: 20) { // Уменьшил общий spacing
                Spacer() // Толкает контент вверх

                // Основной дисплей стрика
                VStack {
                    Text("\(streakCount)")
                        .font(.custom("RFDewi-Bold", size: 140)) // Используем кастомный шрифт и размер из Figma
                        .foregroundColor(.white)
                    Text(streakCount == 1 ? "day streak" : "days streak")
                        .font(.custom("RFDewi-Regular", size: 24)) // Используем кастомный шрифт и размер из Figma
                        .foregroundColor(.gray) // Цвет из Figma (#8A8A8E близок к .gray)
                }
                .padding(.bottom, 40) // Добавил отступ снизу для группы текста

                Spacer() // Толкает кнопки вниз

                // Кнопки действий
                VStack(spacing: 15) { // Уменьшил spacing между кнопками
                    Button("Check In") {
                        performCheckin()
                    }
                    .buttonStyle(PrimaryButtonStyle()) // Стиль из Figma

                    Button("I Relapsed") {
                        performRelapse()
                    }
                    .buttonStyle(SecondaryButtonStyle()) // Стиль из Figma
                }

                // Сообщение для пользователя (если нужно)
                if !message.isEmpty {
                    Text(message)
                        .foregroundColor(.gray)
                        .font(.custom("RFDewi-Regular", size: 14)) // Используем кастомный шрифт
                        .padding(.top, 10) // Небольшой отступ сверху
                        .multilineTextAlignment(.center)
                } else {
                     // Добавляем минимальную высоту, чтобы кнопки не прыгали, когда сообщение появляется/исчезает
                     Spacer().frame(height: 30)
                }

            }
            .padding(.horizontal, 20) // Горизонтальные отступы для всего VStack
            .padding(.bottom, 30) // Нижний отступ
        }
        // Скрываем статус бар для чистого вида
        .statusBar(hidden: true)
    }

    // Логика Check-in
    func performCheckin() {
        let calendar = Calendar.current
        let today = calendar.startOfDay(for: Date())
        let lastDate = calendar.startOfDay(for: lastCheckinDate ?? .distantPast)

        message = "" // Сброс сообщения

        if lastDate == today {
            // Уже сделал чек-ин сегодня
            message = "You've already checked in today."
            return
        }

        let yesterday = calendar.date(byAdding: .day, value: -1, to: today)!

        if lastDate == yesterday {
            // Продолжаем стрик
            streakCount += 1
            message = "Streak continued! Keep going!"
        } else {
            // Начинаем новый стрик (или первый стрик)
            streakCount = 1
            message = "New streak started! You can do it!"
        }

        // Обновляем дату последнего чек-ина на сегодня
        lastCheckinTimestamp = today.timeIntervalSince1970
    }

    // Логика Релапса
    func performRelapse() {
        streakCount = 0
        lastCheckinTimestamp = 0 // Сбрасываем дату, чтобы можно было начать новый стрик сразу
        message = "Streak reset. Remember why you started."
        // TODO: Добавить триггер для In-App Purchase здесь
        print("Relapse confirmed. Triggering IAP flow...") // Placeholder
    }
}

// Стиль основной кнопки (Check In)
struct PrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .frame(maxWidth: .infinity) // Растягиваем по ширине
            .padding(.vertical, 15) // Вертикальный паддинг
            .font(.custom("RFDewi-Semibold", size: 17)) // Шрифт из Figma
            .foregroundColor(.black) // Цвет текста
            .background(Color.white) // Цвет фона
            .cornerRadius(14) // Скругление из Figma
            .scaleEffect(configuration.isPressed ? 0.98 : 1.0) // Легкое уменьшение при нажатии
            .animation(.easeOut(duration: 0.1), value: configuration.isPressed) // Плавная анимация
    }
}

// Стиль второстепенной кнопки (I Relapsed)
struct SecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .frame(maxWidth: .infinity) // Растягиваем по ширине
            .padding(.vertical, 15) // Вертикальный паддинг
            .font(.custom("RFDewi-Semibold", size: 17)) // Шрифт из Figma
            .foregroundColor(.white) // Цвет текста
            .background(Color(red: 0.1, green: 0.1, blue: 0.1)) // Темно-серый фон (#1C1C1E примерно)
            .cornerRadius(14) // Скругление из Figma
            .scaleEffect(configuration.isPressed ? 0.98 : 1.0) // Легкое уменьшение при нажатии
            .animation(.easeOut(duration: 0.1), value: configuration.isPressed) // Плавная анимация
    }
}


struct ContentView_Previews: PreviewProvider {
    static var previews: some View {
        ContentView()
    }
}
// Добавим расширение для удобной работы с HEX цветами, если понадобится в будущем
extension Color {
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let a, r, g, b: UInt64
        switch hex.count {
        case 3: // RGB (12-bit)
            (a, r, g, b) = (255, (int >> 8) * 17, (int >> 4 & 0xF) * 17, (int & 0xF) * 17)
        case 6: // RGB (24-bit)
            (a, r, g, b) = (255, int >> 16, int >> 8 & 0xFF, int & 0xFF)
        case 8: // ARGB (32-bit)
            (a, r, g, b) = (int >> 24, int >> 16 & 0xFF, int >> 8 & 0xFF, int & 0xFF)
        default:
            (a, r, g, b) = (1, 1, 1, 0) // Invalid format, default to black
        }

        self.init(
            .sRGB,
            red: Double(r) / 255,
            green: Double(g) / 255,
            blue:  Double(b) / 255,
            opacity: Double(a) / 255
        )
    }
} 