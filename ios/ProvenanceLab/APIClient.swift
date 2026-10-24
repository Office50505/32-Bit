import Foundation

enum APIClientError: LocalizedError {
    case invalidServerURL
    case invalidResponse
    case server(code: String, message: String)
    case transport(String)

    var errorDescription: String? {
        switch self {
        case .invalidServerURL: "Enter a valid ProvenanceLab server URL in Settings."
        case .invalidResponse: "The server returned an unreadable response."
        case .server(let code, let message): "\(code): \(message)"
        case .transport(let message): message
        }
    }
}

actor APIClient {
    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder
    private var baseURL: URL

    init(baseURL: URL) {
        self.baseURL = baseURL
        let configuration = URLSessionConfiguration.default
        configuration.timeoutIntervalForRequest = 60
        configuration.timeoutIntervalForResource = 180
        configuration.waitsForConnectivity = true
        self.session = URLSession(configuration: configuration)
        self.decoder = JSONDecoder()
        self.decoder.keyDecodingStrategy = .convertFromSnakeCase
        self.encoder = JSONEncoder()
        self.encoder.keyEncodingStrategy = .convertToSnakeCase
    }

    func updateBaseURL(_ url: URL) {
        baseURL = url
    }

    func analyze(_ request: AnalyzeRequest) async throws -> AnalyzeResponse {
        try await send(path: "api/analyze", method: "POST", body: request)
    }

    func createRun(_ requests: [AnalyzeRequest]) async throws -> RunResponse {
        try await send(path: "api/runs", method: "POST", body: BatchAnalyzeRequest(molecules: requests))
    }

    func askBenzo(question: String, currentSmiles: String?) async throws -> BenzoChatResponse {
        try await send(
            path: "api/benzo/chat",
            method: "POST",
            body: BenzoChatRequest(question: question, currentSmiles: currentSmiles)
        )
    }

    func prepareExtractionEngine() async throws -> ExtractionEngineStatus {
        var status: ExtractionEngineStatus = try await send(
            path: "api/extract/image/engine/prepare?hand_drawn=false",
            method: "POST",
            body: Optional<String>.none
        )
        let deadline = Date().addingTimeInterval(600)
        while !status.ready {
            try Task.checkCancellation()
            guard status.stage != "error" else {
                throw APIClientError.server(
                    code: status.errorCode ?? "EXTRACTION_ENGINE_ERROR",
                    message: status.message
                )
            }
            guard Date() < deadline else {
                throw APIClientError.transport("MolNexTR did not finish loading within 10 minutes.")
            }
            try await Task.sleep(for: .milliseconds(750))
            status = try await send(
                path: "api/extract/image/engine?hand_drawn=false",
                method: "GET",
                body: Optional<String>.none
            )
            if status.stage == "not_ready" {
                status = try await send(
                    path: "api/extract/image/engine/prepare?hand_drawn=false",
                    method: "POST",
                    body: Optional<String>.none
                )
            }
        }
        return status
    }

    func extractImage(_ source: ImportedSource) async throws -> ImageExtractionResponse {
        let boundary = "ProvenanceLab-\(UUID().uuidString)"
        let safeFilename = source.filename
            .replacingOccurrences(of: "\r", with: "")
            .replacingOccurrences(of: "\n", with: "")
            .replacingOccurrences(of: "\"", with: "'")
        var body = Data()
        body.appendUTF8("--\(boundary)\r\n")
        body.appendUTF8("Content-Disposition: form-data; name=\"hand_drawn\"\r\n\r\nfalse\r\n")
        body.appendUTF8("--\(boundary)\r\n")
        body.appendUTF8(
            "Content-Disposition: form-data; name=\"image\"; filename=\"\(safeFilename)\"\r\n"
        )
        body.appendUTF8("Content-Type: \(source.mediaType)\r\n\r\n")
        body.append(source.data)
        body.appendUTF8("\r\n--\(boundary)--\r\n")

        var request = URLRequest(url: endpoint("api/extract/image"))
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        request.httpBody = body
        return try await perform(request)
    }

    func downloadReport(runID: String) async throws -> URL {
        var request = URLRequest(url: endpoint("api/runs/\(runID)/report.pdf"))
        request.timeoutInterval = 120
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        let destination = FileManager.default.temporaryDirectory
            .appendingPathComponent("\(runID)-report.pdf")
        try data.write(to: destination, options: .atomic)
        return destination
    }

    private func send<Response: Decodable, Body: Encodable>(
        path: String,
        method: String,
        body: Body?
    ) async throws -> Response {
        var request = URLRequest(url: endpoint(path))
        request.httpMethod = method
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try encoder.encode(body)
        }
        return try await perform(request)
    }

    private func perform<Response: Decodable>(_ request: URLRequest) async throws -> Response {
        do {
            let (data, response) = try await session.data(for: request)
            try validate(response: response, data: data)
            return try decoder.decode(Response.self, from: data)
        } catch is CancellationError {
            throw CancellationError()
        } catch let error as APIClientError {
            throw error
        } catch {
            throw APIClientError.transport(error.localizedDescription)
        }
    }

    private func validate(response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else { throw APIClientError.invalidResponse }
        guard (200...299).contains(http.statusCode) else {
            if let envelope = try? decoder.decode(APIErrorEnvelope.self, from: data) {
                throw APIClientError.server(code: envelope.error.code, message: envelope.error.message)
            }
            throw APIClientError.server(
                code: "HTTP_\(http.statusCode)",
                message: HTTPURLResponse.localizedString(forStatusCode: http.statusCode)
            )
        }
    }

    private func endpoint(_ path: String) -> URL {
        let pieces = path.split(separator: "?", maxSplits: 1).map(String.init)
        var url = baseURL.appendingPathComponent(pieces[0])
        if pieces.count == 2, var components = URLComponents(url: url, resolvingAgainstBaseURL: false) {
            components.percentEncodedQuery = pieces[1]
            url = components.url ?? url
        }
        return url
    }
}

private extension Data {
    mutating func appendUTF8(_ value: String) {
        append(value.data(using: .utf8) ?? Data())
    }
}
